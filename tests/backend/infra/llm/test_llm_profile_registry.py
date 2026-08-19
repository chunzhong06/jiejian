from __future__ import annotations

from pathlib import Path

import pytest
import threading

from product.backend.infra.llm.adapters.base import LLMHttpResponse, LLMTransportError
from product.backend.infra.llm.profiles import LLMProfileRegistry
from product.backend.infra.llm.config import LLMProviderType
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import StorageUnitOfWork, create_session_factory, create_sqlite_engine, upgrade_database


class FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.writes: list[tuple[str, str]] = []
        self.deletes: list[str] = []

    def write(self, secret_ref: str, secret: str) -> None:
        self.values[secret_ref] = secret
        self.writes.append((secret_ref, secret))

    def read(self, secret_ref: str) -> str | None:
        return self.values.get(secret_ref)

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)
        self.deletes.append(secret_ref)

    def configured(self, secret_ref: str | None) -> bool:
        return secret_ref is not None and secret_ref in self.values


class RaisingSecretStore(FakeSecretStore):
    def __init__(self) -> None:
        super().__init__()
        self.error = "sentinel-secret-or-url"
        self.calls: list[str] = []

    def write(self, secret_ref: str, secret: str) -> None:
        self.calls.append("write")
        raise OSError(self.error)

    def read(self, secret_ref: str) -> str | None:
        self.calls.append("read")
        raise OSError(self.error)

    def delete(self, secret_ref: str) -> None:
        self.calls.append("delete")
        raise OSError(self.error)

    def configured(self, secret_ref: str | None) -> bool:
        self.calls.append("configured")
        raise OSError(self.error)


class FakeTransport:
    def __init__(self, response: LLMHttpResponse | None = None, error: str | None = None) -> None:
        self.response = response or LLMHttpResponse(200, b'{"choices":[{"message":{"content":"ok"}}]}')
        self.error = error
        self.calls = []

    def send(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise LLMTransportError(self.error)
        return self.response


class BlockingTransport(FakeTransport):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def send(self, request):
        self.calls.append(request)
        self.started.set()
        self.release.wait(timeout=5)
        return self.response


def _service(
    tmp_path: Path,
    *,
    transport=None,
    store=None,
    now: int = 1,
    inject_clock: bool = True,
):
    database = tmp_path / "profiles.db"
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    factory = create_session_factory(engine)
    clock = iter([now, now, now + 10, now + 10, now + 20, now + 20])
    service = LLMProfileRegistry(
        lambda **kwargs: StorageUnitOfWork(factory, **kwargs),
        transport=transport or FakeTransport(),
        secret_store=store or FakeSecretStore(),
        environ={"ENV_KEY": "env-secret"},
        clock_us=(lambda: next(clock, now + 20)) if inject_clock else None,
    )
    return service, engine


def _values(name: str = "test") -> dict[str, object]:
    return {
        "profile_name": name,
        "provider": LLMProviderType.OPENAI,
        "model": "gpt-test",
        "secret_ref": "env:ENV_KEY",
    }


def test_profile_crud_and_explicit_test_connection_is_single_request(tmp_path: Path) -> None:
    transport = FakeTransport()
    store = FakeSecretStore()
    service, engine = _service(tmp_path, transport=transport, store=store)
    created = service.create(_values(), secret=None)
    assert created.secret_configured is True
    assert created.connection_status == "configured"
    assert transport.calls == []
    assert service.list()[0].profile_name == "test"
    assert service.get("test").connection_status == "configured"
    tested = service.test_connection("test")
    assert tested.connection_status == "available"
    assert len(transport.calls) == 1
    updated = service.update("test", {"model": "gpt-updated"})
    assert updated.model == "gpt-updated"
    engine.dispose()


def test_credential_secret_is_write_only_and_not_in_profile_view(tmp_path: Path) -> None:
    store = FakeSecretStore()
    service, engine = _service(tmp_path, store=store)
    profile = service.create(
        {
            "profile_name": "credential",
            "provider": LLMProviderType.OPENAI,
            "model": "gpt-test",
        },
        secret="not-returned-secret",
    )
    assert profile.secret_ref == "cred:jiejian/llm/credential"
    assert profile.secret_configured is True
    assert "not-returned-secret" not in repr(profile)
    assert "not-returned-secret" not in profile.model_dump_json()
    engine.dispose()


def test_existing_credential_secret_can_be_rotated_without_secret_ref(tmp_path: Path) -> None:
    store = FakeSecretStore()
    service, engine = _service(tmp_path, store=store)
    first = service.create(
        {"profile_name": "rotate", "provider": LLMProviderType.OPENAI, "model": "gpt"},
        secret="old-value",
    )
    updated = service.update("rotate", {"model": "gpt-new"}, secret="new-value")
    assert updated.secret_ref == first.secret_ref == "cred:jiejian/llm/rotate"
    assert store.values == {"cred:jiejian/llm/rotate": "new-value"}
    assert "old-value" not in updated.model_dump_json()
    assert "new-value" not in updated.model_dump_json()
    tested = service.test_connection("rotate")
    assert tested.connection_status == "available"
    assert service._transport.calls[0].headers["authorization"] == "Bearer new-value"
    engine.dispose()


@pytest.mark.parametrize(
    "error,code",
    [
        ("auth_failed", ErrorCode.LLM_AUTH_FAILED),
        ("rate_limited", ErrorCode.LLM_RATE_LIMITED),
        ("timeout", ErrorCode.LLM_TIMEOUT),
        ("provider_unavailable", ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE),
        ("invalid_response", ErrorCode.LLM_INVALID_RESPONSE),
        ("response_too_large", ErrorCode.LLM_BUDGET_EXCEEDED),
    ],
)
def test_connection_errors_are_stable_and_redacted(tmp_path: Path, error: str, code: ErrorCode) -> None:
    service, engine = _service(tmp_path, transport=FakeTransport(error=error))
    service.create(_values())
    with pytest.raises(JiejianError) as captured:
        service.test_connection("test")
    assert captured.value.code == code.value
    assert "ENV_KEY" not in str(captured.value)
    assert service.get("test").error_code == code.value
    engine.dispose()


def test_zero_budget_sends_no_request(tmp_path: Path) -> None:
    transport = FakeTransport()
    service, engine = _service(tmp_path, transport=transport)
    service.create({**_values(), "max_budget_microusd": 0})
    with pytest.raises(JiejianError) as captured:
        service.test_connection("test")
    assert captured.value.code == ErrorCode.LLM_BUDGET_EXCEEDED.value
    assert transport.calls == []
    engine.dispose()


def test_database_failure_compensates_new_credential_without_leaking_secret() -> None:
    store = FakeSecretStore()

    class BrokenProfiles:
        def get(self, _: str):
            return None

        def add(self, _):
            raise RuntimeError("database failed")

    class BrokenWork:
        llm_profiles = BrokenProfiles()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def commit(self):
            raise RuntimeError("database failed")

    service = LLMProfileRegistry(
        lambda **kwargs: BrokenWork(),
        transport=FakeTransport(),
        secret_store=store,
        clock_us=lambda: 1,
    )
    with pytest.raises(JiejianError) as captured:
        service.create(
            {"profile_name": "broken", "provider": LLMProviderType.OPENAI, "model": "gpt"},
            secret="secret-not-in-error",
        )
    assert captured.value.code == ErrorCode.LLM_PROFILE_STORAGE_FAILED.value
    assert "secret-not-in-error" not in str(captured.value)
    assert store.values == {}


def test_profile_persistence_reuses_known_secret_storage_guard(tmp_path: Path) -> None:
    service, engine = _service(tmp_path)
    with pytest.raises(JiejianError) as captured:
        service.create({**_values(), "model": "env-secret"})
    assert captured.value.code == ErrorCode.STORAGE_SECRET.value
    assert "env-secret" not in str(captured.value)
    engine.dispose()


def test_credential_store_failures_are_stable_and_do_not_write(tmp_path: Path) -> None:
    raising = RaisingSecretStore()
    service, engine = _service(tmp_path, store=raising)
    with pytest.raises(JiejianError) as captured:
        service.create(
            {"profile_name": "create-fail", "provider": LLMProviderType.OPENAI, "model": "gpt"},
            secret="new-value",
        )
    assert captured.value.code == ErrorCode.LLM_SECRET_UNAVAILABLE.value
    assert "sentinel-secret-or-url" not in str(captured.value)
    assert raising.calls == ["read"]
    engine.dispose()


def test_credential_store_read_failures_do_not_write_on_update_and_are_hidden_from_views(
    tmp_path: Path,
) -> None:
    store = FakeSecretStore()
    service, engine = _service(tmp_path, store=store)
    service.create(
        {"profile_name": "read-fail", "provider": LLMProviderType.OPENAI, "model": "gpt"},
        secret="old-value",
    )
    raising = RaisingSecretStore()
    service._secret_store = raising
    with pytest.raises(JiejianError) as captured:
        service.update("read-fail", {}, secret="new-value")
    assert captured.value.code == ErrorCode.LLM_SECRET_UNAVAILABLE.value
    assert "sentinel-secret-or-url" not in str(captured.value)
    assert raising.calls == ["read"]
    listed = service.list()
    assert listed[0].secret_configured is False
    assert listed[0].connection_status == "unknown"
    fetched = service.get("read-fail")
    assert fetched.secret_configured is False
    assert "sentinel-secret-or-url" not in repr(fetched)
    with pytest.raises(JiejianError) as captured:
        service.test_connection("read-fail")
    assert captured.value.code == ErrorCode.LLM_SECRET_UNAVAILABLE.value
    assert "sentinel-secret-or-url" not in str(captured.value)
    assert raising.calls == ["read", "configured", "configured", "read", "configured"]
    engine.dispose()


def test_default_clock_produces_real_utc_microseconds(tmp_path: Path) -> None:
    store = FakeSecretStore()
    service, engine = _service(tmp_path, store=store, inject_clock=False)
    profile = service.create(
        {"profile_name": "clock", "provider": LLMProviderType.OPENAI, "model": "gpt"},
        secret="clock-secret",
    )
    assert profile.created_at_us > 0
    assert profile.updated_at_us > 0
    tested = service.test_connection("clock")
    assert tested.tested_at_us is not None and tested.tested_at_us > 0
    engine.dispose()


def test_profile_state_is_invalidated_after_configuration_change(tmp_path: Path) -> None:
    transport = FakeTransport()
    service, engine = _service(tmp_path, transport=transport)
    service.create(_values())
    assert service.test_connection("test").connection_status == "available"
    assert service.update("test", {"model": "changed"}).connection_status == "configured"
    assert service.update("test", {"base_url": "https://example.test/v1"}).connection_status == "configured"
    engine.dispose()


def test_same_profile_connection_test_is_not_queued(tmp_path: Path) -> None:
    transport = BlockingTransport()
    service, engine = _service(tmp_path, transport=transport)
    service.create(_values())
    result: list[object] = []

    worker = threading.Thread(
        target=lambda: result.append(service.test_connection("test")),
        daemon=True,
    )
    worker.start()
    assert transport.started.wait(timeout=5)
    assert service.get("test").connection_status == "testing"
    with pytest.raises(JiejianError) as captured:
        service.test_connection("test")
    assert captured.value.code == ErrorCode.LLM_TEST_IN_PROGRESS.value
    assert len(transport.calls) == 1
    transport.release.set()
    worker.join(timeout=5)
    assert result and result[0].connection_status == "available"
    engine.dispose()
