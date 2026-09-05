# 验证测试账号 API 只公开普通用户元数据，不回显 secret_ref 或秘密正文。

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient as RawTestClient

from product.backend.core.application_understanding import (
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
    candidate_id,
)
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.business_boundary import BusinessActor, boundary_sha256
from tests.fixtures.assurance import actor
from product.backend.core.test_identity import (
    TestIdentityAuthMethod,
    TestIdentityCookie,
)
from product.backend.infra.secrets import credential_ref
from product.backend.infra.storage import ProjectRecord
from product.backend.workflows.test_identities import PreparedLoginState
from tests.fixtures.control_plane import TestClient, create_app
from tests.fixtures.control_plane import TEST_CONTROL_ORIGIN
from product.backend.workflows.test_identities.preparation import IdentityPreparationStatus, IdentityPreparationView


PROJECT_ID = "sample-project"
ROLE_ID = candidate_id("role", "owner")
ACTOR_ID = "bar_" + "1" * 32


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


def test_test_identity_crud_api_excludes_secret_references(tmp_path: Path) -> None:
    store = FakeSecretStore()
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        secret_store=store,
        environ={},
    )
    with app.state.context.uow_factory() as work:
        work.projects.add(
            ProjectRecord(
                project_id=PROJECT_ID,
                name="样例应用",
                status=ProjectStatus.DRAFT,
                created_at_us=1,
                updated_at_us=1,
            )
        )
        work.application_understanding.add(
            ApplicationUnderstanding(
                project_id=PROJECT_ID,
                source_root="D:/sample",
                confirmed_endpoint="http://127.0.0.1:8865",
                endpoint_source_fingerprint="a" * 64,
                endpoint_confirmed_at_us=2,
                endpoint_last_checked_at_us=2,
                endpoint_reachable=True,
                role_candidates=(
                    RoleCandidate(
                        candidate_id=ROLE_ID,
                        canonical_key="owner",
                        display_name="所有者",
                        confidence=CandidateConfidence.HIGH,
                        decision=CandidateDecision.CONFIRMED,
                        origin=CandidateOrigin.MANUAL,
                    ),
                ),
                revision=3,
                created_at_us=1,
                updated_at_us=2,
            )
        )
        revision = actor().model_copy(update={"project_id": PROJECT_ID, "display_name": "所有者"})
        revision = revision.model_copy(update={"semantic_fingerprint": boundary_sha256(revision.semantic_payload())})
        work.business_boundaries.add_actor_revision(revision)
        work.business_boundaries.add_actor(BusinessActor(actor_id=ACTOR_ID, project_id=PROJECT_ID,
            current_revision=1, created_at_us=1, updated_at_us=1))
        work.commit()

    with TestClient(app) as client:
        created = client.post(
            f"/api/projects/{PROJECT_ID}/test-identities",
            json={
                "schema_version": "1",
                "actor_id": ACTOR_ID,
                "actor_revision": 1,
                "label": "所有者账号",
            },
        )
        assert created.status_code == 201
        payload = created.json()["data"]
        assert payload["status"] == "NOT_PREPARED"
        assert "secret_ref" not in created.text

        listed = client.get(f"/api/projects/{PROJECT_ID}/test-identities")
        assert listed.status_code == 200
        assert listed.json()["data"] == [payload]
        assert "secret_ref" not in listed.text

        identity_id = payload["identity_id"]
        secret_ref = credential_ref(
            "test-identity",
            PROJECT_ID,
            identity_id,
            "cookie-00",
        )
        store.write(secret_ref, "api-session-secret")
        app.state.context.test_identities.save_prepared_state(
            identity_id,
            PreparedLoginState(
                auth_method=TestIdentityAuthMethod.COOKIE_SESSION,
                cookies=(
                    TestIdentityCookie(
                        name="session",
                        domain="127.0.0.1",
                        path="/",
                        secure=False,
                        http_only=True,
                        same_site="LAX",
                        value_secret_ref=secret_ref,
                    ),
                ),
                prepared_at_us=payload["updated_at_us"] + 1,
            ),
        )
        prepared = client.get(f"/api/test-identities/{identity_id}")
        assert prepared.status_code == 200
        assert prepared.json()["data"]["status"] == "PREPARED"
        assert "api-session-secret" not in prepared.text
        assert secret_ref not in prepared.text
        prepared_list = client.get(f"/api/projects/{PROJECT_ID}/test-identities")
        assert prepared_list.status_code == 200
        assert "api-session-secret" not in prepared_list.text
        assert secret_ref not in prepared_list.text

        reset = client.post(
            f"/api/test-identities/{identity_id}/reset",
            json={"schema_version": "1"},
        )
        assert reset.status_code == 200

        deleted = client.delete(f"/api/test-identities/{identity_id}")
        assert deleted.status_code == 200
        assert deleted.json()["data"]["deleted"] is True


def _login_view():
    return IdentityPreparationView(preparation_id="prep_" + "1" * 32,
        identity_id="tid_" + "1" * 32, status=IdentityPreparationStatus.STARTING,
        message="正在打开独立登录浏览器…", log_path="var/logs/identity-preparations/test.log")


def test_identity_login_routes_delegate_exact_ids_and_get_does_not_launch(tmp_path, monkeypatch):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=FakeSecretStore(), environ={})
    manager = app.state.context.identity_preparations
    view = _login_view()
    mocks = {name: Mock(return_value=view) for name in ("start", "status", "confirm", "cancel")}
    for name, mock in mocks.items():
        monkeypatch.setattr(manager, name, mock)
    with TestClient(app) as client:
        base = f"/api/identity-preparations/{view.preparation_id}"
        assert client.get(base).json()["data"] == view.model_dump(mode="json")
        mocks["start"].assert_not_called()
        mocks["status"].assert_called_once_with(view.preparation_id)
        for name, path, argument in (
            ("start", f"/api/test-identities/{view.identity_id}/preparations", view.identity_id),
            ("confirm", base + "/confirm", view.preparation_id),
            ("cancel", base + "/cancel", view.preparation_id),
        ):
            response = client.post(path, json={"schema_version": "1"})
            assert response.status_code == 200 and response.json()["data"] == view.model_dump(mode="json")
            mocks[name].assert_called_once_with(argument)


@pytest.mark.parametrize("suffix", ["start", "confirm", "cancel"])
@pytest.mark.parametrize("body", [{}, {"schema_version": 1}, {"schema_version": "2"},
    {"schema_version": "1", "secret_ref": "forbidden"}, {"schema_version": "1", "scope": {}}])
def test_identity_login_posts_reject_non_strict_input(tmp_path, monkeypatch, suffix, body):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=FakeSecretStore(), environ={})
    called = Mock()
    monkeypatch.setattr(app.state.context.identity_preparations, suffix, called)
    view = _login_view()
    path = f"/api/test-identities/{view.identity_id}/preparations" if suffix == "start" else f"/api/identity-preparations/{view.preparation_id}/{suffix}"
    with TestClient(app) as client:
        assert client.post(path, json=body).status_code == 422
    called.assert_not_called()


@pytest.mark.parametrize("suffix", ["start", "status", "confirm", "cancel"])
@pytest.mark.parametrize("authorization", ["no_session", "wrong_origin"])
def test_identity_login_routes_keep_local_control(tmp_path, monkeypatch, suffix, authorization):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=FakeSecretStore(), environ={})
    called = Mock(return_value=_login_view())
    monkeypatch.setattr(app.state.context.identity_preparations, suffix, called)
    view = _login_view()
    path = (f"/api/test-identities/{view.identity_id}/preparations" if suffix == "start" else
            f"/api/identity-preparations/{view.preparation_id}" + ("" if suffix == "status" else f"/{suffix}"))
    client_type = RawTestClient if authorization == "no_session" else TestClient
    with client_type(app, base_url=TEST_CONTROL_ORIGIN) as client:
        headers = {"Origin": TEST_CONTROL_ORIGIN if authorization == "no_session" else "http://127.0.0.1:9999"}
        response = client.get(path, headers=headers) if suffix == "status" else client.post(path, headers=headers, json={"schema_version": "1"})
        # 复用现有 guard：所有 API 验 session/Host，Origin 限制用于写请求。
        read_with_session = suffix == "status" and authorization == "wrong_origin"
        assert response.status_code == (200 if read_with_session else 403)
    if read_with_session:
        called.assert_called_once_with(view.preparation_id)
    else:
        called.assert_not_called()
