# 验证旧准备 writer 保持关闭，有限 ALLOW 技术选择不改变正式权限与 epoch。
from tests.fixtures.control_plane import TestClient, create_app
from tests.fixtures.action_preparation import MemorySecretStore, build_preparation_harness
from tests.fixtures.assurance import permission
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.permission_semantics import PermissionExpectation


def test_old_prepare_safe_writer_remains_absent(tmp_path):
    app = create_app(tmp_path / "var", start_worker=False, environ={})
    with TestClient(app) as client:
        assert client.post("/api/projects/project-1/preparation/prepare-safe").status_code == 404
        assert not any("prepare-safe" in path for path in app.openapi()["paths"])


def test_finite_allow_selection_preserves_permissions_epoch_and_rejects_stale_input(tmp_path):
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    core = app.state.context
    harness = build_preparation_harness(tmp_path, core=core)
    with core.uow_factory() as work:
        for item in (permission(2), permission(3, relation=PermissionIntentRelation.SAME_ROLE_OTHER_ACCOUNT,
                                              expectation=PermissionExpectation.DENY)):
            work.permission_intents.add_revision(item.model_copy(update={"project_id": harness.project_id}))
        work.commit()
    before = core.business_boundaries.view(harness.project_id)
    assert before.permission_statuses[0].allow_control_available
    assert "ALLOW_CONTROL_SELECTION_REQUIRED" not in before.permission_statuses[0].reason_codes
    initial = core.preparation.get(harness.project_id).actions[0]
    control = initial.assurance_contract.allow_controls[0]
    assert len(control.candidate_allow_permissions) == 2 and control.resolved_allow_permission is None
    assert core.workspace.get(harness.project_id).primary_task.task_kind == "SELECT_ALLOW_CONTROL"
    body = dict(schema_version="1", deny_permission=control.deny_permission.model_dump(mode="json"),
        selected_allow_permission=control.candidate_allow_permissions[1].model_dump(mode="json"),
        expected_selection_fingerprint=control.selection_fingerprint)
    route = f"/api/projects/{harness.project_id}/preparation/allow-control"
    with TestClient(app) as client:
        result = client.post(route, json=body)
        assert result.status_code == 200, result.text
        assert client.post(route, json=body).json()["data"] == result.json()["data"]
        assert core.business_boundaries.view(harness.project_id) == before
        selected = core.preparation.get(harness.project_id).actions[0].assurance_contract.allow_controls[0]
        assert selected.resolved_allow_permission == control.candidate_allow_permissions[1]
        assert core.workspace.get(harness.project_id).primary_task.task_kind != "SELECT_ALLOW_CONTROL"
        stale = client.post(route, json=body | {"expected_selection_fingerprint": "f"*64})
        assert stale.status_code == 400, stale.text
        assert stale.json()["error"]["code"] == "STATE_PRECONDITION"
        assert client.post(route, json=body | {"unexpected": True}).status_code == 422
        assert core.business_boundaries.view(harness.project_id) == before
