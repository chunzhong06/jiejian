# 用真实 loopback TARGET/Observer/恢复执行完整 Twin，验证效果而非 HTTP 状态决定三态。

import pytest

from product.backend.domain.lifecycle import CaseVerdict, RunVerdict
from product.backend.infrastructure.execution.check_executor import CheckExecutor
from product.protocols.checks.check_result import check_request_marker
from tests.support.builders.execution.check_target import check_target, execution_configuration






def execute(check_target, tmp_path, **changes):
    request, bundle, input, environment = execution_configuration(check_target, **changes)
    output = CheckExecutor(request, bundle, input, environ=environment, attempt_dir=tmp_path,
        cancellation_requested=lambda: False).execute()
    return output, input


@pytest.mark.parametrize("failure", ["model", "file"])
def test_runner_progress_failure_does_not_change_published_result(check_target, tmp_path, monkeypatch, failure):
    from product.backend.infrastructure.runtime.check_runner import executor as runner
    from product.backend.infrastructure.runtime.jobs.check_requests import CheckRequestStore
    from product.backend.infrastructure.runtime.paths import RuntimePaths
    from product.protocols.checks.check_result import canonical_check_document, parse_check_document, CheckRunnerResult
    request, bundle, input, environment = execution_configuration(check_target, deny_effect=True)
    store = CheckRequestStore(tmp_path)
    store.write(input.job_id, request)
    store.write_bundle(input.job_id, bundle)
    attempt = RuntimePaths(tmp_path).jobs / input.job_id / "attempts" / "1-1"
    attempt.mkdir(parents=True)
    input_path = attempt / "input.json"
    input_path.write_bytes(canonical_check_document(input))
    injected = []
    def rejected(*args, **kwargs):
        injected.append(True)
        raise ValueError("injected progress model failure") if failure == "model" else OSError("injected progress write failure")
    replace = runner.os.replace
    def fail_progress_write(source, destination):
        if destination == attempt / 'progress.json':
            return rejected()
        return replace(source, destination)
    # 全局文件函数只在被测调用期间替换，pytest 报告与清理仍使用真实文件系统。
    with monkeypatch.context() as patch:
        if failure == "model":
            patch.setattr(runner, "CheckRunnerProgress", rejected)
        else:
            patch.setattr(runner.os, "replace", fail_progress_write)
        code = runner.execute_check_attempt(input_path, attempt / "staging", environ=environment)
    assert code == 0 and injected
    result = parse_check_document((attempt / "staging/result.json").read_bytes(), CheckRunnerResult)
    assert result.verdict is RunVerdict.BLOCK
    assert len(check_target[1]["target_calls"]) == 2


@pytest.mark.parametrize("status,effect,expected", [(403, True, RunVerdict.BLOCK), (403, False, RunVerdict.PASS),
    (200, False, RunVerdict.INCONCLUSIVE), (202, False, RunVerdict.INCONCLUSIVE)])
def test_real_twin_matrix_and_each_target_executes_once(check_target, tmp_path, status, effect, expected):
    output, input = execute(check_target, tmp_path, deny_status=status, deny_effect=effect)
    state = check_target[1]
    assert output.result.verdict is expected
    assert len(state["target_calls"]) == len(output.result.case_results) == 2
    first_case = state["cases"][state["target_calls"][0][0]]
    assert first_case.permission.expectation == "ALLOW"
    assert state["value"] == "original" and len(state["recovery_calls"]) == 2
    assert all(marker == check_request_marker(input.run_id, input.job_id, input.attempt, case_id)
        for case_id, marker in state["target_calls"])


@pytest.mark.parametrize("before,after,calls,verdict", [(False, False, 0, RunVerdict.INCONCLUSIVE), (True, False, 2, RunVerdict.BLOCK)])
@pytest.mark.parametrize('runtime_kind',['MANAGED_PYTHON','MANAGED_NODE'])
def test_runtime_drift_stops_unstarted_targets_but_preserves_observed_block(check_target, tmp_path, monkeypatch, before, after, calls, verdict,runtime_kind):
    def controlled(payload):
        reference=dict(instance_id="rti_" + "1" * 32,
            manifest_fingerprint="a" * 64, source_fingerprint=payload["source_fingerprint"],
            process_id=123, process_created_at=456)
        if runtime_kind=='MANAGED_PYTHON':reference['owner_id']='exp_'+'2'*32
        else:reference.update(project_id=payload['project_id'],port=check_target[0],mode='CONTROLLED_NODE_ESM')
        payload.update(runtime=dict(kind=runtime_kind,reference=reference))
    request, bundle, runner_input, environment = execution_configuration(check_target, deny_effect=True, configure=controlled)
    checks = iter((before, after))
    port='node_corresponds' if runtime_kind=='MANAGED_NODE' else 'runtime_corresponds'
    monkeypatch.setattr('product.backend.infrastructure.execution.check_executor.'+port, lambda *_: next(checks))
    monkeypatch.setattr('product.backend.infrastructure.execution.check_executor.controlled_node_executable',lambda _:tmp_path/'node.exe')
    environment["JIEJIAN_VAR_DIR"] = str(tmp_path)
    output = CheckExecutor(request, bundle, runner_input, environ=environment, attempt_dir=tmp_path,
        cancellation_requested=lambda: False).execute()
    assert len(check_target[1]["target_calls"]) == calls
    assert output.result.verdict is verdict
    assert output.result.runtime_correspondence.after == "UNCONFIRMED"
    assert output.result.runtime_correspondence.runtime.kind == runtime_kind


def test_recovery_failure_does_not_erase_confirmed_block(check_target, tmp_path):
    output, _input = execute(check_target, tmp_path, deny_effect=True, recovery_fail=True)
    assert output.result.verdict is RunVerdict.BLOCK
    assert output.result.result_type == "SAFETY_STOPPED"
    assert "RECOVERY_UNVERIFIED" in output.result.cleanup_issues


def test_real_identity_mismatch_prevents_false_attribution(check_target, tmp_path):
    output, _input = execute(check_target, tmp_path, deny_effect=True, identity_mismatch=True)
    assert output.result.verdict is RunVerdict.INCONCLUSIVE
    assert not any(item.verdict is CaseVerdict.VULNERABLE for item in output.result.case_results)


def test_allow_without_effect_invalidates_deny_safe_control(check_target, tmp_path):
    output, _input = execute(check_target, tmp_path, allow_effect=False)
    assert output.result.verdict is RunVerdict.INCONCLUSIVE
    assert all(item.verdict is CaseVerdict.INCONCLUSIVE for item in output.result.case_results)


@pytest.mark.process
@pytest.mark.parametrize("forbidden_effect,expected", [(True, RunVerdict.BLOCK), (False, RunVerdict.PASS)])
def test_independent_worker_runner_real_http_and_fenced_publication(check_target, tmp_path, forbidden_effect, expected):
    import os
    import subprocess
    import time
    from product.backend.bootstrap.worker import WorkerContainer
    from product.backend.domain.lifecycle import JobState, ProjectStatus
    from product.backend.infrastructure.artifacts.checks.check_packages import check_final_directory, validate_check_package
    from product.backend.infrastructure.runtime.jobs.check_requests import CheckRequestStore
    from product.backend.infrastructure.runtime.jobs.models import SubmitJob
    from product.backend.infrastructure.runtime.process.environment import ProcessEnvironmentRole, spawn_python_module
    from product.backend.infrastructure.runtime.process.tree import release_process_tree, terminate_process_tree
    from product.backend.infrastructure.storage.applications.projects import ProjectRecord
    from product.backend.infrastructure.storage.db import default_database_path, prepare_database
    from tests.support.builders.runtime.runtime_environment import runtime_identity_environment

    request, bundle, input, secrets = execution_configuration(check_target, deny_effect=forbidden_effect)
    var_dir = tmp_path / "var"
    prepare_database(default_database_path(var_dir))
    environment = runtime_identity_environment(var_dir, extra=secrets)
    container = WorkerContainer(var_dir, environ=environment)
    process = None
    try:
        now = time.time_ns() // 1000
        with container.uow_factory() as work:
            work.projects.add(ProjectRecord(project_id=request.project_id, name="跨进程检查", status=ProjectStatus.READY,
                created_at_us=now, updated_at_us=now))
            work.commit()
        store = CheckRequestStore(var_dir)
        assert store.write(input.job_id, request)[0] == input.request_hash
        store.write_bundle(input.job_id, bundle)
        container.job_queue.submit(SubmitJob(project_id=request.project_id, operation_type="CHECK", idempotency_key="real-check",
            request_hash=input.request_hash, plan_fingerprint=request.plan_fingerprint, source_fingerprint=request.source_fingerprint,
            policy_epoch=request.policy_epoch, engine_version=request.engine_version, max_attempts=1,
            available_at_us=now, now_us=now, run_id=input.run_id, job_id=input.job_id))
        names = tuple(sorted(secrets))
        args = ["--var-dir", str(var_dir), "--job-id", input.job_id, "--lease-owner", input.lease_owner]
        for name in names:
            args.extend(("--secret-name", name))
        log_path = container.paths.logs / "check-cross-process.log"
        with log_path.open("w+b") as stream:
            process = spawn_python_module(environment, "product.backend.interfaces.worker.job", *args,
                role=ProcessEnvironmentRole.WORKER, secret_names=names, cwd=container.paths.temp,
                stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, close_fds=True)
            code = process.wait(timeout=40)
            stream.seek(0)
            diagnostic = stream.read(8192).decode("utf-8", errors="replace")
        assert code == 0, diagnostic
        release_process_tree(process)
        with container.uow_factory() as work:
            assert work.jobs.get(input.job_id).state is JobState.SUCCEEDED
            assert work.runs.get(input.run_id).verdict is expected
            assert work.check_publications.get(input.run_id).attempt == 1
            assert len(work.evidence.list_for_run(input.run_id)) == 2
        package = validate_check_package(check_final_directory(var_dir, request.project_id, input.run_id), published=True)
        assert package.result.verdict is expected
        from product.backend.application.checks.reading.results import CheckResultReader
        from product.backend.application.checks.reading.story import CheckStoryBuilder
        reader = CheckResultReader(var_dir=var_dir, uow_factory=container.uow_factory)
        story = CheckStoryBuilder(reader).build(input.run_id)
        assert story.verdict is expected
        assert len(story.actions) == 2
        assert "schema_version" not in story.model_dump()
        deny_story = next(item for item in story.actions if item.permission.expectation == "DENY")
        assert deny_story.fact_comparison.verified_actual_identity.verification_status == "MATCH"
        assert all(item.fact_comparison.effects[0].business_label == bundle.actions[0].proofs[0].business_label
            for item in story.actions)
        assert all(len(item.decisive_proof_chain) <= 4 and item.repair_requirement is None for item in story.actions)
        if forbidden_effect:
            assert deny_story.breakpoint.precision.value == "VIOLATION_ONLY"
        else:
            assert deny_story.breakpoint is None
        assert len(check_target[1]["target_calls"]) == 2
        assert all(pid not in (0, os.getpid(), process.pid) for pid in check_target[1]["caller_pids"])
    finally:
        if process is not None:
            terminate_process_tree(process, 2) if process.poll() is None else release_process_tree(process)
        container.close()

pytestmark = [pytest.mark.level4]
