# 验证测试账号 API 只公开普通用户元数据，不回显 secret_ref 或秘密正文。

from __future__ import annotations

from pathlib import Path

from product.backend.core.application_understanding import (
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
    candidate_id,
)
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.test_identity import (
    TestIdentityAuthMethod,
    TestIdentityCookie,
)
from product.backend.infra.secrets import credential_ref
from product.backend.infra.storage import ProjectRecord
from product.backend.workflows.test_identities import PreparedLoginState
from tests.fixtures.control_plane import TestClient, create_app


PROJECT_ID = "sample-project"
ROLE_ID = candidate_id("role", "owner")


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
        work.commit()

    with TestClient(app) as client:
        created = client.post(
            f"/api/projects/{PROJECT_ID}/test-identities",
            json={
                "schema_version": "1",
                "role_candidate_id": ROLE_ID,
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
