from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from jiejian.api import create_app
from jiejian.contracts.llm.adapters.base import LLMHttpResponse, LLMTransportError


class FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def write(self, secret_ref: str, secret: str) -> None:
        self.values[secret_ref] = secret

    def read(self, secret_ref: str) -> str | None:
        return self.values.get(secret_ref)

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)

    def configured(self, secret_ref: str | None) -> bool:
        return secret_ref is not None and secret_ref in self.values


class FakeTransport:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.calls = 0

    def send(self, request):
        self.calls += 1
        if self.error is not None:
            raise LLMTransportError(self.error)
        return LLMHttpResponse(200, b'{"choices":[{"message":{"content":"ok"}}]}')


def _payload(**overrides: object) -> dict[str, object]:
    return {
        "profile_name": "api-test",
        "provider": "openai",
        "model": "gpt-test",
        "secret": "value-a",
        **overrides,
    }


def test_profile_api_is_write_only_and_test_is_explicitly_single_request(
    tmp_path: Path,
) -> None:
    transport = FakeTransport()
    store = FakeSecretStore()
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        llm_transport=transport,
        llm_secret_store=store,
        clock_us=lambda: 1,
    )
    with TestClient(app) as client:
        created = client.post("/api/v1/llm/profiles", json=_payload())
        assert created.status_code == 201
        assert "value-a" not in created.text
        assert created.json()["data"]["secret_ref"] == "cred:jiejian/llm/api-test"
        assert transport.calls == 0

        listed = client.get("/api/v1/llm/profiles")
        assert listed.status_code == 200
        assert transport.calls == 0
        tested = client.post("/api/v1/llm/profiles/api-test/test")
        assert tested.status_code == 200
        assert tested.json()["data"]["connection_status"] == "available"
        assert transport.calls == 1


def test_profile_api_rejects_unsafe_values_and_maps_stable_transport_error(
    tmp_path: Path,
) -> None:
    transport = FakeTransport(error="auth_failed")
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        llm_transport=transport,
        environ={"ENV_KEY": "env-secret"},
        clock_us=lambda: 1,
    )
    with TestClient(app) as client:
        invalid = client.post(
            "/api/v1/llm/profiles",
            json=_payload(base_url="https://user:password@example.com/v1"),
        )
        assert invalid.status_code == 422
        assert "password" not in invalid.text

        created = client.post(
            "/api/v1/llm/profiles",
            json=_payload(secret=None, secret_ref="env:ENV_KEY"),
        )
        assert created.status_code == 201
        tested = client.post("/api/v1/llm/profiles/api-test/test")
        assert tested.status_code == 401
        assert tested.json()["error"]["code"] == "llm_auth_failed"
        assert "env-secret" not in tested.text


def test_profile_api_paths_are_versioned_in_openapi(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False)
    paths = app.openapi()["paths"]
    assert "/api/v1/llm/profiles" in paths
    assert "/api/v1/llm/profiles/{profile_name}/test" in paths


def test_profile_api_rotates_existing_credential_without_secret_ref(
    tmp_path: Path,
) -> None:
    store = FakeSecretStore()
    transport = FakeTransport()
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        llm_transport=transport,
        llm_secret_store=store,
    )
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/llm/profiles",
            json=_payload(),
        )
        assert created.status_code == 201
        assert store.values["cred:jiejian/llm/api-test"] == "value-a"

        rotated = client.patch(
            "/api/v1/llm/profiles/api-test",
            json={"secret": "value-b"},
        )
        assert rotated.status_code == 200
        assert store.values["cred:jiejian/llm/api-test"] == "value-b"
        assert rotated.json()["data"]["secret_ref"] == "cred:jiejian/llm/api-test"
        assert "value-a" not in rotated.text
        assert "value-b" not in rotated.text
