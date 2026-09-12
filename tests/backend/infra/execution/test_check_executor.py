# 用真实 loopback TARGET/Observer/恢复执行完整 Twin，验证效果而非 HTTP 状态决定三态。
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from product.backend.core.lifecycle import CaseVerdict, RunVerdict
from product.backend.infra.execution.check_executor import CheckExecutor
from product.protocols.check_result import CheckAssetReference, CheckRunnerInput, check_request_marker
from product.protocols.execution_v3 import canonical_execution_request_v3_bytes
from tests.fixtures.check_execution import execution_pair


@pytest.fixture
def check_target():
    state = dict(value="original", deny_status=403, deny_effect=False, allow_effect=True,
        recovery_fail=False, identity_mismatch=False, cases={}, target_calls=[], recovery_calls=[], caller_pids=[])
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload):
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            if self.path.startswith("/tasks/"):
                marker = self.path.rsplit("/", 1)[-1]
                task_state = state.get("task_state", "SUCCESS")
                return self.reply(200, dict(schema_version="1", case_tag=marker,
                    resource_id="resource-1", task_id=None if task_state == "NOT_CREATED" else "task-" + marker,
                    state=task_state, final_result=None))
            if self.path == "/identity":
                token = self.headers.get("Authorization", "").removeprefix("Bearer ")
                subject = "subject-" + token.removeprefix("credential-")
                case = state["cases"].get(self.headers.get("X-Jiejian-Case-ID"))
                if state["identity_mismatch"] and case is not None and case.permission.expectation == "DENY" and token == state.get("deny_token"):
                    subject = "unmapped-subject"
                return self.reply(200, {"subject_id": subject})
            return self.reply(200, dict(resource_id="resource-1", workflow_state="DRAFT", value=state["value"]))
        def do_POST(self):
            case_id = self.headers.get("X-Jiejian-Case-ID")
            if self.path.startswith("/restore/"):
                state["recovery_calls"].append(case_id)
                if state["recovery_fail"] and state["cases"][case_id].permission.expectation == "DENY":
                    return self.reply(500, {})
                state["value"] = "original"
                return self.reply(200, {})
            case = state["cases"][case_id]
            deny = case.permission.expectation == "DENY"
            state["target_calls"].append((case_id, self.headers.get("X-Jiejian-Request-ID")))
            state["caller_pids"].append(int(self.headers.get("X-Jiejian-Runner-PID", "0")))
            if state["deny_effect"] if deny else state["allow_effect"]:
                state["value"] = "changed-by-" + case_id
            # 发布链测试在真实 TARGET 完成时落审计事件，保持请求标记与副作用同源。
            if state.get("after_target") is not None:
                state["after_target"](case, self.headers.get("X-Jiejian-Request-ID"))
            return self.reply(state["deny_status"] if deny else state.get("allow_status", 200), {})
        def log_message(self, *_args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def execution_configuration(check_target, *, configure=None, **changes):
    port, state = check_target
    state.update(changes)
    request, bundle = execution_pair(port=port, state_changing=True, configure=configure)
    state["cases"] = {case.case_id: case for action in request.actions for case in action.cases}
    environment = {identity.binding.secret_ref.removeprefix("env:"): f"credential-{index}"
        for index, identity in enumerate(bundle.identities, 1)}
    deny = next(case for case in state["cases"].values() if case.permission.expectation == "DENY")
    deny_identity = next(identity for identity in bundle.identities if identity.identity_id == deny.subject_test_identity_id)
    state["deny_token"] = environment[deny_identity.binding.secret_ref.removeprefix("env:")]
    request_hash = hashlib.sha256(canonical_execution_request_v3_bytes(request)).hexdigest()
    input = CheckRunnerInput(run_id="run_" + "1" * 32, job_id="job_" + "2" * 32,
        attempt=1, lease_owner="check-worker", fencing_token=1, created_at_us=1,
        request_hash=request_hash, config_hash=request.config_fingerprint,
        assets=(CheckAssetReference(logical_id="request", sha256=request_hash),
            CheckAssetReference(logical_id="runtime", sha256=request.config_fingerprint)))
    return request, bundle, input, environment


def execute(check_target, tmp_path, **changes):
    request, bundle, input, environment = execution_configuration(check_target, **changes)
    output = CheckExecutor(request, bundle, input, environ=environment, attempt_dir=tmp_path,
        cancellation_requested=lambda: False).execute()
    return output, input


@pytest.mark.parametrize("failure", ["model", "file"])
def test_runner_progress_failure_does_not_change_result_or_call_legacy_evaluator(check_target, tmp_path, monkeypatch, failure):
    from product.backend.infra.runtime.check_runner import executor as runner
    from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
    from product.backend.infra.runtime.paths import RuntimePaths
    from product.protocols.check_result import canonical_check_document, parse_check_document, CheckRunnerResult
    request, bundle, input, environment = execution_configuration(check_target, deny_effect=True)
    store = CheckRequestStore(tmp_path)
    store.write(input.job_id, request)
    store.write_bundle(input.job_id, bundle)
    attempt = RuntimePaths(tmp_path).jobs / input.job_id / "attempts" / "1-1"
    attempt.mkdir(parents=True)
    input_path = attempt / "input.json"
    input_path.write_bytes(canonical_check_document(input))
    def rejected(*args, **kwargs):
        raise ValueError("injected progress model failure") if failure == "model" else OSError("injected progress write failure")
    if failure == "model":
        monkeypatch.setattr(runner, "CheckRunnerProgress", rejected)
    else:
        monkeypatch.setattr(runner.os, "replace", rejected)
    def legacy_forbidden(*args, **kwargs):
        raise AssertionError("legacy accepted-alone evaluator must not run")
    monkeypatch.setattr("product.backend.core.verification.permissions.evaluation.evaluate_permission_case", legacy_forbidden)
    assert runner.execute_check_attempt(input_path, attempt / "staging", environ=environment) == 0
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
    from product.backend.composition.worker import WorkerContainer
    from product.backend.core.lifecycle import JobState, ProjectStatus
    from product.backend.infra.artifacts.check_packages import check_final_directory, validate_check_package
    from product.backend.infra.runtime.jobs.check_requests import CheckRequestStore
    from product.backend.infra.runtime.jobs.models import SubmitJob
    from product.backend.infra.runtime.process.environment import ProcessEnvironmentRole, spawn_python_module
    from product.backend.infra.runtime.process.tree import release_process_tree, terminate_process_tree
    from product.backend.infra.storage import ProjectRecord, default_database_path, upgrade_database
    from tests.fixtures.runtime_environment import runtime_identity_environment

    request, bundle, input, secrets = execution_configuration(check_target, deny_effect=forbidden_effect)
    var_dir = tmp_path / "var"
    upgrade_database(default_database_path(var_dir))
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
            process = spawn_python_module(environment, "product.backend.infra.runtime.worker.process", *args,
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
        from product.backend.workflows.checks.results import CheckResultReader
        from product.backend.workflows.checks.story import CheckStoryBuilder
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
