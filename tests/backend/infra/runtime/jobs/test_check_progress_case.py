# 验证当前考题只来自已校验冻结资产；与执行顺序一致，读取失败仅降级说明。
import json
import socket
import sqlite3
import subprocess
from types import SimpleNamespace as N
from unittest.mock import Mock

import pytest
from sqlalchemy import event

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.artifacts.check_publication import CheckPublisher
from product.backend.infra.execution.check_executor import CheckExecutor
from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
from product.backend.workflows.checks.results import CheckResultReader
from product.protocols.check_result import CheckRunnerProgress, canonical_check_document
from product.protocols.check_runtime import parse_check_runtime
from product.protocols.execution_v3 import PersistedExecutionRequestV3
from tests.fixtures.check_publication import package_parts, NOW
from tests.fixtures.action_preparation import MemorySecretStore
from tests.fixtures.check_plan import prepared_action
from tests.fixtures.control_plane import create_app, TestClient


def frozen_labels(payload):
    for index, identity in enumerate(payload["identities"]):
        identity["label"] = f"冻结账号 {index}"
    payload["actions"][0]["display_name"] = "读取归属资源"


pytestmark = pytest.mark.parametrize("package_parts", [
    {"prepared": prepared_action(superset=True), "configure": frozen_labels}], indirect=True)


@pytest.fixture
def progress_parts(package_parts):
    var_dir, factory, job, staging, result = package_parts
    request = PersistedExecutionRequestV3.model_validate_json((staging / "request.json").read_bytes())
    bundle = parse_check_runtime((staging / "runtime.json").read_bytes())
    store = CheckRequestStore(var_dir)
    store.write(job.job_id, request)
    store.write_bundle(job.job_id, bundle)
    with factory() as work:
        run = work.runs.get(job.run_id)
    return N(var_dir=var_dir, factory=factory, job=job, run=run, staging=staging,
        result=result, request=request, bundle=bundle, store=store,
        reader=CheckResultReader(var_dir=var_dir, uow_factory=factory))


def write_progress(parts, **changes):
    count = sum(len(action.cases) for action in parts.request.actions)
    progress = CheckRunnerProgress(run_id=parts.job.run_id, job_id=parts.job.job_id, attempt=parts.job.attempt,
        fencing_token=parts.job.fencing_token, request_hash=parts.job.request_hash, phase="EXECUTING",
        completed_cases=0, planned_cases=count, observed_at_us=NOW+12).model_copy(update=changes)
    (parts.staging.parent / "progress.json").write_bytes(canonical_check_document(progress))
    return progress


def test_current_case_matches_executor_order_and_copies_only_frozen_labels(progress_parts):
    parts = progress_parts
    projected, executed = [], []
    results = {item.case_id: item for item in parts.result.case_results}
    def progress(phase, completed, planned):
        write_progress(parts, phase=phase, completed_cases=completed, planned_cases=planned)
        status = parts.reader.status(parts.job.run_id)
        if phase == "EXECUTING":
            assert status.run.verdict is None and status.result_integrity == "NOT_PUBLISHED"
            projected.append(status.progress.current_case)
        else:
            assert status.progress.current_case is None
    def case(action, configured, current, control):
        executed.append(current.case_id)
        return results[current.case_id], None
    # 只运行 execute 的真实排序/进度循环；单题执行和所有 I/O 由无副作用 stub 替代。
    executor = N(request=parts.request, bundle=parts.bundle, input=parts.result, clock=lambda: NOW+12,
        cancelled=lambda: False, progress=progress, _case=case, web=N(close=Mock()),
        _stopped=None, _first_error=None, _cleanup_issues=[])
    CheckExecutor.execute(executor)
    assert [item.case_id for item in projected] == executed
    assert [item.expectation for item in projected] == ["ALLOW", "ALLOW", "DENY"]
    identities = {item.identity_id: item for item in parts.bundle.identities}
    configured = {item.action_id: item for item in parts.bundle.actions}
    cases = {case.case_id: (action, case) for action in parts.request.actions for case in action.cases}
    for item in projected:
        action, current = cases[item.case_id]
        assert item.action_label == "读取归属资源"
        assert item.planned_subject_label == identities[current.subject_test_identity_id].label
        assert item.planned_resource_owner_label == identities[current.resource_owner_test_identity_id].label
        assert item.resource_id == current.resource_id
        proofs = {proof.binding_fingerprint: proof for proof in configured[action.action_id].proofs}
        assert item.effect_labels == tuple(dict.fromkeys(proofs[proof.binding_fingerprint].business_label for proof in current.proof_requirements))
        assert set(item.model_dump()) == {"case_id", "action_label", "expectation", "planned_subject_label",
            "planned_resource_owner_label", "resource_id", "effect_labels"}
    assert projected[-1].planned_subject_label != projected[-1].planned_resource_owner_label


@pytest.mark.parametrize("phase,completed,planned,has_progress", [
    ("PREPARING", 0, 3, True), ("FINALIZING", 0, 3, True), ("EXECUTING", 3, 3, True),
    ("EXECUTING", 0, 4, True), ("EXECUTING", 4, 3, False), ("EXECUTING", -1, 3, False)])
def test_phase_and_counts_never_guess_current_case(progress_parts, phase, completed, planned, has_progress):
    if has_progress:
        write_progress(progress_parts, phase=phase, completed_cases=completed, planned_cases=planned)
    else:
        # canonical 编码器会拒绝非法计数；负向 Reader 场景直接写损坏字节，不放宽正式协议。
        payload = write_progress(progress_parts, phase=phase).model_dump(mode="json")
        payload.update(completed_cases=completed, planned_cases=planned)
        (progress_parts.staging.parent / "progress.json").write_text(json.dumps(payload), encoding="utf-8")
    progress = progress_parts.reader.status(progress_parts.job.run_id).progress
    if has_progress:
        assert progress.phase == phase and progress.completed_cases == completed and progress.planned_cases == planned
        assert progress.current_case is None
    else:
        assert progress is None


@pytest.mark.parametrize("asset,mutation", [("request", "missing"), ("request", "hash"), ("bundle", "missing"), ("bundle", "hash")])
def test_missing_or_corrupt_asset_preserves_coarse_progress(progress_parts, asset, mutation):
    parts = progress_parts
    write_progress(parts)
    path = parts.store.path_for(parts.job.job_id, config_hash=parts.request.config_fingerprint if asset == "bundle" else None)
    if mutation == "missing": path.unlink()
    else: path.write_bytes(path.read_bytes()+b" ")
    status = parts.reader.status(parts.job.run_id)
    assert status.progress.phase == "EXECUTING" and status.progress.completed_cases == 0
    assert status.progress.current_case is None
    assert status.run.verdict is None and status.result_integrity == "NOT_PUBLISHED"


@pytest.mark.parametrize("target,field,value", [
    ("run", "project_id", "other"), ("run", "source_fingerprint", "0"*64),
    ("run", "plan_fingerprint", "0"*64), ("run", "policy_epoch", 99), ("run", "engine_version", "other"),
    ("job", "project_id", "other"), ("job", "run_id", "run_"+"0"*32), ("job", "request_hash", "0"*64)])
def test_frozen_request_and_job_must_match_run(progress_parts, target, field, value):
    parts = progress_parts
    write_progress(parts)
    run = N(**{name: getattr(parts.run, name) for name in ("run_id", "project_id", "request_hash",
        "source_fingerprint", "plan_fingerprint", "policy_epoch", "engine_version")})
    job = N(**{name: getattr(parts.job, name) for name in ("job_id", "operation_type", "state", "attempt",
        "fencing_token", "run_id", "project_id", "request_hash")})
    setattr(run if target == "run" else job, field, value)
    progress = parts.reader._progress(run, job)
    assert progress is not None and progress.current_case is None and progress.planned_cases == 3


def test_fencing_and_config_validation_keep_existing_fail_closed_boundaries(progress_parts, monkeypatch):
    parts = progress_parts
    write_progress(parts, fencing_token=parts.job.fencing_token+1)
    assert parts.reader.status(parts.job.run_id).progress is None
    write_progress(parts)
    def invalid(*args):
        raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID, "执行快照格式无效")
    monkeypatch.setattr("product.backend.workflows.checks.results.validate_check_inputs", invalid)
    assert parts.reader.status(parts.job.run_id).progress.current_case is None
    def programming_error(*args):
        raise RuntimeError("unexpected programmer failure")
    monkeypatch.setattr("product.backend.workflows.checks.results.validate_check_inputs", programming_error)
    with pytest.raises(RuntimeError, match="unexpected programmer"):
        parts.reader.status(parts.job.run_id)


def test_published_status_keeps_verdict_and_clears_current_case(progress_parts):
    parts = progress_parts
    write_progress(parts)
    assert parts.reader.status(parts.job.run_id).progress.current_case is not None
    package = CheckPublisher(parts.var_dir, parts.factory, clock_us=lambda: NOW+20).publish(parts.staging)
    status = parts.reader.status(parts.job.run_id)
    assert status.result_integrity == "VALID" and status.run.verdict == package.result.verdict
    assert status.progress.phase == "FINALIZING" and status.progress.current_case is None


def test_status_get_is_read_only_and_does_not_resolve_live_identity(progress_parts, worker_services, monkeypatch):
    parts = progress_parts
    write_progress(parts, completed_cases=2)
    with sqlite3.connect(worker_services.database_path) as source, sqlite3.connect(parts.var_dir / "data/jiejian.db") as destination:
        source.backup(destination)
    app = create_app(parts.var_dir, start_worker=False, secret_store=MemorySecretStore(), environ={})
    with TestClient(app) as client:
        context = app.state.context
        forbidden = Mock(side_effect=AssertionError("current case GET must only read frozen facts"))
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        monkeypatch.setattr(subprocess, "Popen", forbidden)
        monkeypatch.setattr(CheckExecutor, "execute", forbidden)
        monkeypatch.setattr("product.backend.infra.artifacts.check_validation.validate_check_decisions", forbidden)
        monkeypatch.setattr(context.test_identities, "list", forbidden)
        monkeypatch.setattr(context.secret_store, "read", forbidden)
        with context.check_results._uow_factory() as work:
            engine = work._require_session().get_bind()
        statements = []
        def capture(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement.lstrip().split()[0].upper())
        event.listen(engine, "before_cursor_execute", capture)
        try:
            response = client.get(f"/api/runs/{parts.job.run_id}")
        finally:
            event.remove(engine, "before_cursor_execute", capture)
        assert response.status_code == 200
        value = response.json()["data"]
        assert value["run"]["verdict"] is None and value["result_integrity"] == "NOT_PUBLISHED"
        current = value["progress"]["current_case"]
        assert current["expectation"] == "DENY"
        assert current["planned_subject_label"] != current["planned_resource_owner_label"]
        assert "schema_version" not in current and "secret_ref" not in response.text
        assert set(statements) <= {"SELECT", "PRAGMA"}
        forbidden.assert_not_called()
