# 验证 1.1.1 Business Boundary 首次建立、持续维护与决策 HTTP 边界。

from __future__ import annotations

from pathlib import Path

from tests.fixtures.control_plane import TestClient, create_app
from product.backend.workflows.business_boundaries.official_recipe import (
    official_boundary_recipe,
)


def _proposal_payload() -> dict[str, object]:
    return {
        "schema_version": "1",
        "proposed_actors": [
            {
                "item_id": "pactr_1111111111111111",
                "write_mode": "CREATE",
                "display_name": "项目负责人",
                "description": "负责项目交付与数据管理",
                "effective_state": "ACTIVE",
            }
        ],
        "proposed_actions": [
            {
                "item_id": "pactn_1111111111111111",
                "write_mode": "CREATE",
                "display_name": "导出完整项目交付包",
                "description": "形成可交付的完整项目包",
                "primary_resource_concept": "项目交付空间",
                "operation_kind": "EXPORT",
                "state_changing": True,
                "effect_catalog": [
                    {
                        "item_id": "peff_1111111111111111",
                        "business_label": "完整项目交付包真实形成",
                        "effect_kind": "OBJECT_CREATION",
                        "resource_concept": "项目交付包",
                        "description": "交付包已经形成",
                    }
                ],
                "effective_state": "ACTIVE",
            }
        ],
        "proposed_permissions": [
            {
                "item_id": "pperm_1111111111111111",
                "write_mode": "CREATE",
                "effective_state": "ACTIVE",
                "subject_actor_item_id": "pactr_1111111111111111",
                "business_action_item_id": "pactn_1111111111111111",
                "resource_owner_actor_item_id": "pactr_1111111111111111",
                "relation": "OWNS",
                "expectation": "ALLOW",
                "protected_effect_item_ids": ["peff_1111111111111111"],
            }
        ],
        "provenance": "本机界鉴用户通过控制面提交",
    }


def test_business_boundary_api_approves_bundle_and_creates_actor_identity(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(tmp_path / "var", start_worker=False, environ={})

    with TestClient(app) as client:
        connected = client.post(
            "/api/applications/connect",
            json={
                "schema_version": "1",
                "source_root": str(source),
                "project_name": "业务边界 API 测试",
            },
        )
        assert connected.status_code == 201
        project_id = connected.json()["data"]["project"]["project_id"]

        created = client.post(
            f"/api/projects/{project_id}/business-boundaries/proposals",
            json=_proposal_payload(),
        )
        assert created.status_code == 201, created.text
        proposal = created.json()["data"]["proposal"]
        assert proposal["proposed_actors"][0]["actor_id"] is None

        approved = client.post(
            f"/api/projects/{project_id}/business-boundaries/proposals/"
            f"{proposal['proposal_id']}/approve",
            json={
                "schema_version": "1",
                "expected_fingerprint": proposal["proposal_fingerprint"],
                "reason": "确认稳定业务边界",
            },
        )
        assert approved.status_code == 200
        boundary = approved.json()["data"]
        assert boundary["policy_epoch"] == 1
        assert len(boundary["actors"]) == 1
        assert len(boundary["actions"]) == 1
        assert boundary["actor_bindings"][0]["status"] == "MISSING"
        assert boundary["action_bindings"][0]["status"] == "MISSING"
        assert len(boundary["permission_intents"]) == 1
        assert boundary["permission_statuses"][0]["allow_control_available"] is True

        actor = boundary["actors"][0]
        identity = client.post(
            f"/api/projects/{project_id}/test-identities",
            json={
                "schema_version": "1",
                "actor_id": actor["actor_id"],
                "actor_revision": actor["revision"],
                "label": "负责人账号",
            },
        )
        assert identity.status_code == 201
        assert identity.json()["data"]["actor_id"] == actor["actor_id"]
        assert "role_candidate_id" not in identity.text


def test_official_boundary_recipe_remains_a_pure_asset() -> None:
    recipe = official_boundary_recipe()

    assert [item.display_name for item in recipe.actors] == [
        "项目负责人",
        "普通协作成员",
    ]
    assert [item.display_name for item in recipe.actions] == [
        "导出完整项目交付包",
        "查看日常协作资料",
    ]
    assert len(recipe.permissions) == 3
    assert recipe.actions[0].effects[0].business_label == "完整项目交付包真实形成"


def test_old_write_surfaces_are_not_registered(tmp_path: Path) -> None:
    app = create_app(tmp_path / "var", start_worker=False, environ={})
    with TestClient(app) as client:
        for path in (
            "/api/projects/sample-project/permission-intents",
            "/api/projects/sample-project/checks",
            "/api/projects/sample-project/recordings",
            "/api/projects/sample-project/runs",
            "/api/projects/sample-project/preparation",
            "/api/projects/sample-project/business-boundaries/official-recipe",
            "/api/projects/sample-project/business-boundaries/official-recipe/proposal",
        ):
            assert client.post(path, json={"schema_version": "1"}).status_code == 404


def test_business_boundary_maintenance_api_uses_desired_state_not_write_modes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    app = create_app(tmp_path / "var", start_worker=False, environ={})

    with TestClient(app) as client:
        connected = client.post(
            "/api/applications/connect",
            json={
                "schema_version": "1",
                "source_root": str(source),
                "project_name": "业务边界维护 API 测试",
            },
        )
        project_id = connected.json()["data"]["project"]["project_id"]
        initial = client.post(
            f"/api/projects/{project_id}/business-boundaries/proposals",
            json=_proposal_payload(),
        ).json()["data"]["proposal"]
        approved = client.post(
            f"/api/projects/{project_id}/business-boundaries/proposals/"
            f"{initial['proposal_id']}/approve",
            json={
                "schema_version": "1",
                "expected_fingerprint": initial["proposal_fingerprint"],
                "reason": "确认首次业务边界",
            },
        )
        assert approved.status_code == 200

        draft_response = client.get(
            f"/api/projects/{project_id}/business-boundaries/maintenance-draft"
        )
        assert draft_response.status_code == 200, draft_response.text
        draft = draft_response.json()["data"]
        assert "write_mode" not in draft["actors"][0]
        assert draft["actors"][0]["actor_id"] is not None
        draft["actors"][0]["description"] += "，包含 API 维护"
        created = client.post(
            f"/api/projects/{project_id}/business-boundaries/maintenance-proposals",
            json={
                "schema_version": "1",
                "expected_boundary_state_fingerprint": draft[
                    "boundary_state_fingerprint"
                ],
                "actors": draft["actors"],
                "actions": draft["actions"],
                "permissions": draft["permissions"],
                "provenance": "本机用户通过维护 API 提交",
            },
        )
        assert created.status_code == 201, created.text
        proposal_view = created.json()["data"]
        assert proposal_view["proposal"]["proposed_actors"][0]["write_mode"] == (
            "APPEND_REVISION"
        )
        assert proposal_view["change_summary"]["business_revision_updates"]

        initial_again = client.post(
            f"/api/projects/{project_id}/business-boundaries/proposals",
            json=_proposal_payload(),
        )
        assert initial_again.status_code == 409
        assert initial_again.json()["error"]["code"] == "BOUNDARY_MAINTENANCE_REQUIRED"

        proposal = proposal_view["proposal"]
        maintenance_approved = client.post(
            f"/api/projects/{project_id}/business-boundaries/proposals/"
            f"{proposal['proposal_id']}/approve",
            json={
                "schema_version": "1",
                "expected_fingerprint": proposal["proposal_fingerprint"],
                "reason": "确认维护提案",
            },
        )
        assert maintenance_approved.status_code == 200, maintenance_approved.text
        assert maintenance_approved.json()["data"]["actors"][0]["revision"] == 2
