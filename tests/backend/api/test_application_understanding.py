# 验证普通用户应用连接、地址发现、确认与 readiness API 共用同一项目事实。

from __future__ import annotations

import json
from pathlib import Path

from tests.fixtures.control_plane import TestClient, create_app
from product.backend.workflows.application_understanding.endpoints import (
    EndpointProbeObservation,
    TargetEndpointDiscovery,
)
from product.backend.core.test_identity import TestIdentityAuthMethod, TestIdentityCookie
from product.backend.infra.secrets import credential_ref
from product.backend.workflows.test_identities import PreparedLoginState
from tests.fixtures.collaboration_golden import InMemorySecretStore


def _reachable_discovery(endpoint: str) -> TargetEndpointDiscovery:
    def probe(candidate: str, _limits) -> EndpointProbeObservation:
        return EndpointProbeObservation(
            reachable=candidate == endpoint,
            status_code=200 if candidate == endpoint else None,
            detail="测试服务已响应" if candidate == endpoint else "测试服务未响应",
        )

    return TargetEndpointDiscovery(probe=probe)


def test_application_connection_confirms_endpoint_without_profile(
    tmp_path: Path,
) -> None:
    endpoint = "http://127.0.0.1:4555"
    source = tmp_path / "source"
    source.mkdir()
    (source / "openapi.json").write_text(
        json.dumps(
                {
                    "openapi": "3.1.0",
                    "x-roles": ["owner"],
                    "servers": [{"url": endpoint}],
                "components": {
                    "securitySchemes": {
                        "oauth": {
                            "type": "oauth2",
                            "flows": {
                                "clientCredentials": {
                                    "tokenUrl": "/token",
                                    "scopes": {"owner": "所有者"},
                                }
                            },
                        }
                    }
                },
                "paths": {
                    "/documents": {
                        "get": {"operationId": "listDocuments", "summary": "查看文档"}
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    app = create_app(tmp_path / "var", start_worker=False)
    app.state.context.application_understanding.endpoint_discovery = (
        _reachable_discovery(endpoint)
    )
    with TestClient(app) as client:
        connected = client.post(
            "/api/applications/connect",
            json={"schema_version": "1", "source_root": str(source)},
        )
        assert connected.status_code == 201
        assert connected.json()["schema_version"] == "1"
        connection = connected.json()["data"]
        assert "schema_version" not in connection
        assert connection["project"]["status"] == "DRAFT"

        project_id = connection["project"]["project_id"]
        with app.state.context.uow_factory() as work:
            assert work.execution_profiles.list_for_project(project_id) == ()

        candidates = client.post(f"/api/projects/{project_id}/endpoint-candidates")
        assert candidates.status_code == 200
        assert "schema_version" not in candidates.json()["data"]
        assert candidates.json()["data"]["candidates"][0]["endpoint"] == endpoint

        confirmed = client.put(
            f"/api/projects/{project_id}/endpoint",
            json={"schema_version": "1", "endpoint": endpoint, "revision": 0},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["data"]["confirmed_endpoint"] == endpoint
        assert confirmed.json()["data"]["revision"] == 1

        understanding = client.get(
            f"/api/projects/{project_id}/application-understanding"
        )
        assert understanding.status_code == 200
        assert "schema_version" not in understanding.json()["data"]
        assert understanding.json()["data"]["confirmed_endpoint"] == endpoint

        product_status = client.get(f"/api/projects/{project_id}/status")
        assert product_status.status_code == 200
        readiness = product_status.json()["data"]["readiness"]
        assert "schema_version" not in readiness
        assert readiness["endpoint_status"] == "CONFIRMED"
        assert readiness["next_required_action"] == "AUTHORIZE_SOURCE_ANALYSIS"
        assert product_status.json()["data"]["primary_attention_key"] == (
            "authorize-source-analysis"
        )
        assert product_status.json()["data"]["attention_items"][0]["key"] == (
            "authorize-source-analysis"
        )

        authorized = client.put(
            f"/api/projects/{project_id}/source-analysis-authorization",
            json={"schema_version": "1", "authorized": True, "revision": 1},
        )
        assert authorized.status_code == 200
        assert authorized.json()["data"]["source_analysis_authorized"] is True

        analyzed = client.post(
            f"/api/projects/{project_id}/source-analysis",
            json={"schema_version": "1", "revision": 2},
        )
        assert analyzed.status_code == 200
        assert analyzed.json()["data"]["role_candidates"][0]["canonical_key"] == "owner"
        assert (
            analyzed.json()["data"]["action_candidates"][0]["canonical_key"]
            == "GET /documents"
        )

        role = analyzed.json()["data"]["role_candidates"][0]
        action = analyzed.json()["data"]["action_candidates"][0]
        decided_role = client.put(
            f"/api/projects/{project_id}/roles/{role['candidate_id']}",
            json={
                "schema_version": "1",
                "decision": "CONFIRMED",
                "display_name": "所有者",
                "revision": 3,
            },
        )
        assert decided_role.status_code == 200
        decided_action = client.put(
            f"/api/projects/{project_id}/actions/{action['candidate_id']}",
            json={
                "schema_version": "1",
                "decision": "CONFIRMED",
                "display_name": "查看文档",
                "revision": 4,
            },
        )
        assert decided_action.status_code == 200
        delivery = client.post(f"/api/projects/{project_id}/delivery-check")
        assert delivery.status_code == 200
        assert delivery.json()["data"]["decision"] == "BLOCKED"
        assert delivery.json()["data"]["reason_codes"] == [
            "TRUSTED_RESULT_MISSING"
        ]
        assert delivery.json()["data"]["next_path"] == "/validation"
        manual_role = client.post(
            f"/api/projects/{project_id}/roles",
            json={"schema_version": "1", "display_name": "访客", "revision": 5},
        )
        assert manual_role.status_code == 201
        manual_action = client.post(
            f"/api/projects/{project_id}/actions",
            json={
                "schema_version": "1",
                "display_name": "导出记录",
                "risk_hint": "READ",
                "revision": 6,
            },
        )
        assert manual_action.status_code == 201
        assert manual_action.json()["data"]["revision"] == 7

        excluded = client.put(
            f"/api/projects/{project_id}/roles/{role['candidate_id']}",
            json={
                "schema_version": "1",
                "decision": "REJECTED",
                "display_name": "所有者",
                "revision": 7,
            },
        )
        assert excluded.status_code == 200
        proposed = client.put(
            f"/api/projects/{project_id}/roles/{role['candidate_id']}",
            json={
                "schema_version": "1",
                "decision": "PROPOSED",
                "display_name": "所有者",
                "revision": 8,
            },
        )
        assert proposed.status_code == 200
        detected_after = next(
            item
            for item in proposed.json()["data"]["role_candidates"]
            if item["candidate_id"] == role["candidate_id"]
        )
        assert detected_after["decision"] == "PROPOSED"

        manual_candidate = next(
            item
            for item in proposed.json()["data"]["role_candidates"]
            if item["origin"] == "MANUAL"
        )
        invalid_manual_history = client.put(
            f"/api/projects/{project_id}/roles/{manual_candidate['candidate_id']}",
            json={
                "schema_version": "1",
                "decision": "PROPOSED",
                "display_name": manual_candidate["display_name"],
                "revision": 9,
            },
        )
        assert invalid_manual_history.status_code == 400
        assert (
            invalid_manual_history.json()["error"]["code"]
            == "ONBOARDING_INPUT_INVALID"
        )


def test_application_endpoint_rejects_non_loopback_address(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")

    app = create_app(tmp_path / "var", start_worker=False)
    with TestClient(app) as client:
        connected = client.post(
            "/api/applications/connect",
            json={"schema_version": "1", "source_root": str(source)},
        )
        project_id = connected.json()["data"]["project"]["project_id"]
        rejected = client.put(
            f"/api/projects/{project_id}/endpoint",
            json={
                "schema_version": "1",
                "endpoint": "https://example.com",
                "revision": 0,
            },
        )

        assert rejected.status_code == 400
        assert rejected.json()["error"]["code"] == "APPLICATION_ENDPOINT_INVALID"


def test_application_endpoint_rejects_the_active_control_origin_before_probe(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    probes: list[str] = []

    def probe(candidate: str, _limits) -> EndpointProbeObservation:
        probes.append(candidate)
        return EndpointProbeObservation(
            reachable=True,
            status_code=200,
            detail="不应执行的探测",
        )

    app = create_app(tmp_path / "var", start_worker=False)
    app.state.context.application_understanding.endpoint_discovery = (
        TargetEndpointDiscovery(probe=probe)
    )
    with TestClient(app) as client:
        connected = client.post(
            "/api/applications/connect",
            json={"schema_version": "1", "source_root": str(source)},
        )
        project_id = connected.json()["data"]["project"]["project_id"]
        rejected = client.put(
            f"/api/projects/{project_id}/endpoint",
            json={
                "schema_version": "1",
                "endpoint": "http://127.0.0.1:8765",
                "revision": 0,
            },
        )
        understanding = client.get(
            f"/api/projects/{project_id}/application-understanding"
        )

    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "SELF_TARGET_FORBIDDEN"
    assert rejected.json()["error"]["message"] == (
        "当前地址是界鉴自身服务，请填写实际被检查应用地址"
    )
    assert probes == []
    assert understanding.json()["data"]["confirmed_endpoint"] is None


def test_remove_application_archives_history_cleans_secrets_and_same_source_restores(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    endpoint = "http://127.0.0.1:4555"
    (source / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "x-roles": ["owner"],
                "servers": [{"url": endpoint}],
                "paths": {"/exports": {"post": {"summary": "导出资料"}}},
            }
        ),
        encoding="utf-8",
    )
    secrets = InMemorySecretStore()
    app = create_app(
        tmp_path / "var",
        start_worker=False,
        secret_store=secrets,
        clock_us=lambda: 10,
    )
    app.state.context.application_understanding.endpoint_discovery = (
        _reachable_discovery(endpoint)
    )

    with TestClient(app) as client:
        connected = client.post(
            "/api/applications/connect",
            json={"schema_version": "1", "source_root": str(source)},
        ).json()["data"]
        project_id = connected["project"]["project_id"]
        confirmed_endpoint = client.put(
            f"/api/projects/{project_id}/endpoint",
            json={"schema_version": "1", "endpoint": endpoint, "revision": 0},
        ).json()["data"]
        authorized = client.put(
            f"/api/projects/{project_id}/source-analysis-authorization",
            json={"schema_version": "1", "authorized": True, "revision": confirmed_endpoint["revision"]},
        ).json()["data"]
        analyzed = client.post(
            f"/api/projects/{project_id}/source-analysis",
            json={"schema_version": "1", "revision": authorized["revision"]},
        ).json()["data"]
        role = analyzed["role_candidates"][0]
        confirmed_role = client.put(
            f"/api/projects/{project_id}/roles/{role['candidate_id']}",
            json={"schema_version": "1", "decision": "CONFIRMED", "display_name": "负责人", "revision": analyzed["revision"]},
        ).json()["data"]
        identity = app.state.context.test_identities.create(
            project_id,
            role_candidate_id=confirmed_role["role_candidates"][0]["candidate_id"],
            label="历史账号",
        )
        identity_id = identity.identity_id
        secret_ref = credential_ref(
            "test-identity",
            project_id,
            identity_id,
            "cookie-00",
        )
        secrets.write(secret_ref, "opaque-test-session")
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
                prepared_at_us=11,
            ),
        )

        removed = client.delete(f"/api/projects/{project_id}")
        normal_list = client.get("/api/projects")
        historical_list = client.get("/api/projects?include_archived=true")

        assert removed.status_code == 200
        assert removed.json()["data"]["status"] == "ARCHIVED"
        assert normal_list.json()["data"] == []
        assert historical_list.json()["data"][0]["project_id"] == project_id
        assert historical_list.json()["data"][0]["status"] == "ARCHIVED"
        assert secrets.configured(secret_ref) is False
        with app.state.context.uow_factory() as work:
            retained = work.test_identities.get(identity_id)
            assert retained is not None
            assert retained.prepared_at_us == 11
            assert retained.secret_refs == (secret_ref,)

        restored = client.post(
            "/api/applications/connect",
            json={"schema_version": "1", "source_root": str(source)},
        )
        assert restored.status_code == 201
        assert restored.json()["data"]["project"]["project_id"] == project_id
        assert restored.json()["data"]["project"]["status"] == "DRAFT"
        assert client.get("/api/projects").json()["data"][0]["project_id"] == project_id
