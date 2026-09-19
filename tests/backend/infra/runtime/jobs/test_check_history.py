# 验证有界历史的真实仓储分页与严格发布读取，不以数据库 Verdict 或未知标签替代发布事实。
import json
import socket
import sqlite3
import subprocess
from unittest.mock import Mock

import pytest
from sqlalchemy import event

from product.backend.core.lifecycle import RunLifecycle, RunVerdict
from product.backend.infra.storage import RunRecord
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.workflows.checks.results import CheckResultReader
from tests.fixtures.check_publication import build_package_parts, package_parts, NOW
from tests.fixtures.check_execution import execution_pair
from tests.fixtures.action_preparation import MemorySecretStore
from tests.fixtures.control_plane import create_app, TestClient


def add_runs(factory, project, values):
    with factory() as work:
        for number, created, lifecycle in values:
            work.runs.add(RunRecord(run_id=f"run_{number:032x}", project_id=project, request_hash="a"*64,
                plan_fingerprint="b"*64, source_fingerprint="c"*64, policy_epoch=1, engine_version="test",
                lifecycle=lifecycle, verdict=RunVerdict.PASS if lifecycle is RunLifecycle.COMPLETED else None,
                created_at_us=created, updated_at_us=created))
        work.commit()


def test_keyset_ties_cursor_project_scope_and_new_top_do_not_repeat(package_parts):
    var_dir, factory, job, _, _ = package_parts
    add_runs(factory, job.project_id, [(3, NOW+100, RunLifecycle.FAILED), (1, NOW+100, RunLifecycle.FAILED),
        (2, NOW+100, RunLifecycle.FAILED), (4, NOW+90, RunLifecycle.CANCELLED)])
    add_runs(factory, "job-runtime-project", [(5, NOW+100, RunLifecycle.QUEUED)])
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    first = reader.history(job.project_id, limit=2)
    assert [item.status.run.run_id for item in first.items] == [f"run_{i:032x}" for i in (1, 2)]
    assert first.next_cursor.run_id == f"run_{2:032x}"
    add_runs(factory, job.project_id, [(6, NOW+200, RunLifecycle.QUEUED)])
    second = reader.history(job.project_id, limit=2, before_created_at_us=first.next_cursor.created_at_us,
        before_run_id=first.next_cursor.run_id)
    assert [item.status.run.run_id for item in second.items] == [f"run_{i:032x}" for i in (3, 4)]
    final = reader.history(job.project_id, before_created_at_us=second.next_cursor.created_at_us,
        before_run_id=second.next_cursor.run_id)
    assert [item.status.run.run_id for item in final.items] == [job.run_id] and final.next_cursor is None
    foreign_cursor = reader.history(job.project_id, before_created_at_us=NOW+100, before_run_id=f"run_{5:032x}")
    assert all(item.status.run.project_id == job.project_id for item in foreign_cursor.items)
    assert f"run_{5:032x}" not in [item.status.run.run_id for item in foreign_cursor.items]


def test_scan_budget_returns_empty_page_with_last_scanned_cursor(package_parts, monkeypatch):
    var_dir, factory, job, _, _ = package_parts
    add_runs(factory, job.project_id, [(i, NOW+1000-i, RunLifecycle.FAILED) for i in range(1, 252)])
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    original = reader._status_and_package
    scanned = []
    def checked(work, run):
        scanned.append(run.run_id)
        return original(work, run)
    monkeypatch.setattr(reader, "_status_and_package", checked)
    page = reader.history(job.project_id, query="absent text")
    assert page.items == () and len(scanned) == 250
    assert page.next_cursor.run_id == f"run_{250:032x}"
    last = reader.history(job.project_id, before_created_at_us=page.next_cursor.created_at_us,
        before_run_id=page.next_cursor.run_id, query="absent text")
    assert last.items == () and last.next_cursor is None and len(scanned) == 252


def test_real_publication_labels_search_and_corruption_never_use_db_verdict(package_parts, monkeypatch):
    var_dir, factory, job, directory, _ = package_parts
    package = CheckPublisher(var_dir, factory, clock_us=lambda: NOW+20).publish(directory)
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    checked = Mock(wraps=reader._package)
    monkeypatch.setattr(reader, "_package", checked)
    label = package.bundle.actions[0].display_name
    page = reader.history(job.project_id, query="  " + label.swapcase() + "  ", verdict=RunVerdict.INCONCLUSIVE)
    assert len(page.items) == 1 and page.items[0].action_labels == (label,)
    assert checked.call_count == 1
    assert page.items[0].change_id is None and page.items[0].source_run_id is None
    assert reader.history(job.project_id, query=".*").items == ()
    assert len(reader.history(job.project_id, query=job.run_id.upper()).items) == 1
    (package.directory / "result.json").write_bytes(b"{}")
    invalid = reader.history(job.project_id).items[0]
    assert invalid.status.result_integrity == "INVALID" and invalid.status.run.verdict is None
    assert invalid.action_labels == () and invalid.change_id is None and invalid.source_run_id is None
    assert reader.history(job.project_id, query=label).items == ()
    assert reader.history(job.project_id, verdict=RunVerdict.INCONCLUSIVE).items == ()
    add_runs(factory, job.project_id, [(1, NOW+100, RunLifecycle.COMPLETED)])
    assert reader.history(job.project_id, verdict=RunVerdict.PASS).items == ()


@pytest.mark.parametrize("context_kind", ["change", "repair"])
def test_history_copies_references_only_from_verified_request(worker_services, tmp_path, context_kind):
    from product.protocols.execution_v3 import PersistedExecutionRequestV3
    change_id, source_run_id = "change_history", "run_" + "f" * 32

    frozen, bundle = execution_pair()
    payload = frozen.model_dump(mode="json")
    cases = [case for action in frozen.actions for case in action.cases]
    permissions = {case.permission.intent_id: case.permission.model_dump(mode="json",
        include={"intent_id", "revision", "intent_hash"}) for case in cases}
    if context_kind == "change":
        payload["change_context"] = dict(change_id=change_id, impact_fingerprint="d" * 64,
            required_intent_ids=sorted(permissions))
    else:
        allow = next(case for case in cases if case.permission.expectation == "ALLOW")
        payload["repair_context"] = dict(repair_reference="e" * 64, source_run_id=source_run_id,
            original_policy_epoch=frozen.policy_epoch,
            original_intents=[permissions[key] for key in sorted(permissions)],
            selected_allow_permission=permissions[allow.permission.intent_id], resource_id=allow.resource_id,
            resource_owner_test_identity_id=allow.resource_owner_test_identity_id,
            owner_identity_fingerprint=allow.owner_identity_fingerprint,
            must_disappear_effect_ids=list(allow.permission.protected_effect_ids),
            original_evidence_standard_fingerprints=["d" * 64], allow_regression_case_fingerprints=[])
    frozen = PersistedExecutionRequestV3.model_validate_json(json.dumps(payload))

    # 在队列、证据和发布收据计算哈希之前注入冻结上下文，仍走真实 Publisher 与 Reader。
    var_dir, factory, job, staging, _ = build_package_parts(
        worker_services, tmp_path, request=frozen, bundle=bundle)
    package = CheckPublisher(var_dir, factory, clock_us=lambda: NOW+20).publish(staging)
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    item = reader.history(job.project_id).items[0]
    assert item.status.result_integrity == "VALID"
    assert item.change_id == (change_id if context_kind == "change" else None)
    assert item.source_run_id == (source_run_id if context_kind == "repair" else None)
    (package.directory / "request.json").write_bytes(b"{}")
    invalid = reader.history(job.project_id).items[0]
    assert invalid.status.result_integrity == "INVALID"
    assert invalid.change_id is None and invalid.source_run_id is None


@pytest.mark.parametrize("lifecycle", [RunLifecycle.QUEUED, RunLifecycle.RUNNING, RunLifecycle.FAILED,
    RunLifecycle.CANCELLED, RunLifecycle.SAFETY_STOPPED])
def test_unpublished_lifecycle_does_not_become_verdict(package_parts, lifecycle):
    var_dir, factory, job, _, _ = package_parts
    add_runs(factory, job.project_id, [(1, NOW+100, lifecycle)])
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    item = reader.history(job.project_id, query=f"run_{1:032x}", lifecycle=lifecycle).items[0]
    assert item.status.run.lifecycle is lifecycle and item.status.run.verdict is None
    assert item.status.result_integrity == "NOT_PUBLISHED" and item.action_labels == ()
    assert reader.history(job.project_id, query=f"run_{1:032x}", verdict=RunVerdict.PASS).items == ()


def test_active_uses_one_project_filtered_candidate_without_publication_scan(package_parts, monkeypatch):
    var_dir, factory, job, _, _ = package_parts
    add_runs(factory, job.project_id, [(3, NOW+100, RunLifecycle.QUEUED), (2, NOW+100, RunLifecycle.RUNNING),
        (1, NOW+200, RunLifecycle.FAILED), (4, NOW+300, RunLifecycle.COMPLETED)])
    add_runs(factory, "job-runtime-project", [(5, NOW+500, RunLifecycle.RUNNING)])
    reader = CheckResultReader(var_dir=var_dir, uow_factory=factory)
    monkeypatch.setattr(reader, "_package", Mock(side_effect=AssertionError("must not scan historical publication")))
    assert reader.active_for_project(job.project_id).run.run_id == f"run_{2:032x}"


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"query": "x"*129},
    {"before_created_at_us": -1, "before_run_id": "run_"+"0"*32}, {"before_created_at_us": 0},
    {"before_run_id": "run_"+"0"*32}, {"before_created_at_us": 0, "before_run_id": "bad"},
    {"verdict": "SAFE"}, {"lifecycle": "FINISHED"}])
def test_history_api_rejects_invalid_queries(package_parts, worker_services, params):
    var_dir, _, job, _, _ = package_parts
    with sqlite3.connect(worker_services.database_path) as source, sqlite3.connect(var_dir / "data/jiejian.db") as destination:
        source.backup(destination)
    app = create_app(var_dir, start_worker=False, secret_store=MemorySecretStore(), environ={})
    with TestClient(app) as client:
        response = client.get(f"/api/projects/{job.project_id}/check-history", params=params)
        assert response.status_code in (400, 422)
        assert response.json()["error"]["code"] == "INPUT_INVALID"


def test_history_api_keeps_runs_shape_and_is_read_only(package_parts, worker_services, monkeypatch):
    var_dir, factory, job, staging, _ = package_parts
    CheckPublisher(var_dir, factory, clock_us=lambda: NOW+20).publish(staging)
    with sqlite3.connect(worker_services.database_path) as source, sqlite3.connect(var_dir / "data/jiejian.db") as destination:
        source.backup(destination)
    app = create_app(var_dir, start_worker=False, secret_store=MemorySecretStore(), environ={})
    with TestClient(app) as client:
        forbidden = Mock(side_effect=AssertionError("history is read only"))
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        monkeypatch.setattr(subprocess, "Popen", forbidden)
        monkeypatch.setattr("product.backend.core.verification.checks.evaluate_check_case", forbidden)
        monkeypatch.setattr(app.state.context.project_repair, "evaluate", forbidden)
        with app.state.context.uow_factory() as work:
            engine = work._require_session().get_bind()
        statements = []
        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.lstrip().split()[0].upper())
        event.listen(engine, "before_cursor_execute", capture)
        try:
            value = client.get(f"/api/projects/{job.project_id}/check-history").json()["data"]
            old = client.get(f"/api/projects/{job.project_id}/runs").json()["data"]
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert value["project_id"] == job.project_id and value["next_cursor"] is None
        assert [item["status"] for item in value["items"]] == old
        assert "schema_version" not in value and "schema_version" not in value["items"][0]
        assert set(statements) <= {"SELECT", "PRAGMA"}
        forbidden.assert_not_called()
        assert client.get("/api/projects/missing/check-history").status_code == 404
        client.cookies.clear()
        assert client.get(f"/api/projects/{job.project_id}/check-history").status_code == 403
