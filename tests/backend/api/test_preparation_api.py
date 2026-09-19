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
        assert stale.status_code == 409, stale.text
        assert stale.json()["error"]["code"] == "STATE_PRECONDITION"
        assert client.post(route, json=body | {"unexpected": True}).status_code == 422
        assert core.business_boundaries.view(harness.project_id) == before


def test_evidence_details_get_is_guarded_read_only_and_has_no_write_routes(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from sqlalchemy import select
    from product.backend.infra.storage.base import Base
    from product.backend.infra.storage.unit_of_work import StorageUnitOfWork

    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    core = app.state.context
    harness = build_preparation_harness(tmp_path, core=core)
    route = f"/api/projects/{harness.project_id}/preparation/evidence/{harness.action.action_id}"

    def snapshot():
        # 覆盖绑定、权限、epoch、Run/Job 以及其余持久表，避免只比较页面投影。
        with core.engine.connect() as connection:
            return {table.name: sorted((tuple(row) for row in connection.execute(select(table))), key=repr)
                    for table in Base.metadata.sorted_tables}

    with TestClient(app) as client:
        before = snapshot()
        forbidden = Mock(side_effect=AssertionError("read route attempted a write or plan"))
        monkeypatch.setattr(StorageUnitOfWork, "commit", forbidden)
        monkeypatch.setattr(core.preparation, "current_plan", forbidden)
        monkeypatch.setattr(core.preparation, "build_execution_request_v3", forbidden)
        monkeypatch.setattr(core.preparation_bindings, "register_observer", forbidden)
        response = client.get(route)
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["action_label"] == harness.action.display_name
        assert data["effects"][0]["source_label"] == "尚无证明材料"
        assert data["effects"][0]["material_status"] == "NEEDS_USER"
        assert client.get(route).json() == response.json()
        assert client.get(route.replace(harness.action.action_id, "missing-action")).status_code == 404
        assert client.get(route.replace(harness.project_id, "missing-project")).status_code == 404
        for method in (client.post, client.put, client.delete):
            assert method(route).status_code == 405
        assert snapshot() == before
        forbidden.assert_not_called()
        client.cookies.clear()
        assert client.get(route).status_code == 403


def test_evidence_details_exception_does_not_leak_reader_message(tmp_path, monkeypatch):
    from unittest.mock import Mock
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    core = app.state.context
    harness = build_preparation_harness(tmp_path, core=core)
    monkeypatch.setattr(core.preparation_bindings, "describe_evidence",
        Mock(side_effect=RuntimeError("private-path-and-credential-marker")))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/projects/{harness.project_id}/preparation/evidence/{harness.action.action_id}")
        assert response.status_code == 500
        assert "private-path-and-credential-marker" not in response.text


def test_existing_registered_binding_missing_runtime_is_described_without_repair(tmp_path):
    from product.backend.core.action_preparation import ActionEvidenceBinding, ActionEvidenceKind, RegisteredObserverReference, seal_binding
    app = create_app(tmp_path / "var", start_worker=False, secret_store=MemorySecretStore(), environ={})
    core = app.state.context
    harness = build_preparation_harness(tmp_path, core=core)
    with core.uow_factory() as work:
        binding = seal_binding(ActionEvidenceBinding,
            **core.preparation_bindings._common(work, harness.action, harness.identities[0],
                work.application_understanding.get(harness.project_id), 100, harness.identities[0].identity_id),
            kind=ActionEvidenceKind.REGISTERED_OBSERVER, effect_id=harness.effect_id,
            observer_reference=RegisteredObserverReference(descriptor_id="exp_" + "b"*32,
                descriptor_fingerprint="a"*64, observer_id="saved-observer"))
        work.action_preparation.replace(binding)
        work.commit()
    before = core.preparation.get(harness.project_id)
    with TestClient(app) as client:
        response = client.get(f"/api/projects/{harness.project_id}/preparation/evidence/{harness.action.action_id}")
        assert response.status_code == 200, response.text
        item = response.json()["data"]["effects"][0]
        assert item["material_status"] == "STALE"
        assert item["binding_fingerprint"] == binding.binding_fingerprint
        assert item["source_kind"] == "REGISTERED_OBSERVER" and item["registered_source_available"] is False
        assert item["closure_supported"] is None and "REGISTERED_OBSERVER_UNAVAILABLE" in item["reason_codes"]
        assert binding.observer_reference.descriptor_id not in response.text and "saved-observer" not in response.text
        assert core.preparation.get(harness.project_id) == before
        with core.uow_factory() as work:
            assert work.action_preparation.evidence(harness.action.action_id, 1, harness.effect_id) == binding
