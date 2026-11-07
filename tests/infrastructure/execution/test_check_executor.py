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

@pytest.mark.parametrize('forbidden,expected',[(False,RunVerdict.PASS),(True,RunVerdict.BLOCK)])
def test_business_sequence_uses_same_runner_restores_and_survives_publisher_validation(check_target,tmp_path,forbidden,expected):
    import hashlib,json
    from product.backend.domain.errors import JiejianError
    from product.backend.domain.checks.plan import ProjectCheckPlan,ActionCheckPlan
    from product.backend.domain.checks.scenarios import compile_business_scenario
    from product.protocols.checks.scenarios import BusinessScenarioRevision
    from product.protocols.checks.execution_request import ExecutionRequest,canonical_execution_request_bytes
    from product.protocols.checks.check_result import CheckAssetReference
    from product.backend.infrastructure.artifacts.checks.check_validation import validate_check_decisions
    from types import SimpleNamespace as NS
    request,bundle,input,environment=execution_configuration(check_target,deny_effect=forbidden)
    source=ProjectCheckPlan(project_id=request.project_id,source_fingerprint=request.source_fingerprint,policy_epoch=request.policy_epoch,
        engine_version=request.engine_version,actions=tuple(ActionCheckPlan(**action.model_dump(),gaps=()) for action in request.actions),
        gaps=(),plan_fingerprint=request.plan_fingerprint)
    def invocation(expectation):
        case=next(case for case in request.actions[0].cases if case.permission.expectation==expectation)
        return dict(id='execute',label='准确规则下的真实动作',items=[dict(id='resource',
            permission={name:getattr(case.permission,name) for name in ('intent_id','revision','intent_hash')},
            subject_identity_id=case.subject_test_identity_id,resource_id=case.resource_id)])
    document=BusinessScenarioRevision.model_validate_json(json.dumps(dict(id='bsc_'+'2'*32,project_id=request.project_id,revision=1,label='换主体实验',
        experiments=[dict(id='normal',label='正常',kind='NORMAL',invocations=[invocation('ALLOW')]),
            dict(id='other_subject',label='换主体',kind='CHANGE_SUBJECT',control_experiment_id='normal',invocations=[invocation('DENY')])])))
    compiled=compile_business_scenario(source,document,bundle)
    assert not compiled.gaps
    raw=request.model_dump(mode='json')
    raw.update(actions=[item.model_dump(mode='json',exclude={'gaps'}) for item in compiled.actions],
        scenario=compiled.scenario.model_dump(mode='json'),plan_fingerprint=compiled.plan_fingerprint)
    request=ExecutionRequest.model_validate_json(json.dumps(raw))
    digest=hashlib.sha256(canonical_execution_request_bytes(request)).hexdigest()
    input=input.model_copy(update=dict(request_hash=digest,assets=(CheckAssetReference(logical_id='request',sha256=digest),
        CheckAssetReference(logical_id='runtime',sha256=request.config_fingerprint))))
    check_target[1]['cases']={case.case_id:case for action in request.actions for case in action.cases}
    output=CheckExecutor(request,bundle,input,environ=environment,attempt_dir=tmp_path,cancellation_requested=lambda:False).execute()
    assert output.result.verdict is expected
    assert len(check_target[1]['target_calls'])==len(output.result.case_results)==2
    assert check_target[1]['value']=='original'
    assert all(item.outcome.recovery_verified for item in output.result.case_results)
    validate_check_decisions(NS(request=request,result=output.result,evidence=output.evidence))
    from product.backend.infrastructure.artifacts.checks.scenario_progress import read_scenario_journal
    journal=read_scenario_journal(tmp_path/'scenario-execution.json',request,input)
    assert all(item.request=='RECEIVED' and item.recovered_cases==item.recovery_intents==item.case_ids for item in journal.nodes)
    # 即使旧进程已经结束，同一 attempt 也不能因重新构造执行器而重放节点。
    with pytest.raises(JiejianError):
        CheckExecutor(request,bundle,input,environ=environment,attempt_dir=tmp_path,cancellation_requested=lambda:False)
    assert len(check_target[1]['target_calls'])==2


@pytest.mark.parametrize('response_kind',['complete','missing','duplicate'])
def test_http_batch_is_sent_once_preserves_duplicates_and_separates_response_items(check_target,response_kind):
    """只验证真实 HTTP 适配边界；不把这一项测试当作完整权限判断。"""
    import json
    from product.backend.infrastructure.execution.web.check_runtime import CheckWebRuntime
    from product.protocols.web.request import HttpRequestTemplate
    from product.protocols.checks.scenarios import ScenarioInvocation
    request,bundle,_,environment=execution_configuration(check_target)
    base=next(case for case in request.actions[0].cases if case.permission.expectation=='ALLOW')
    members=(base,base.model_copy(update=dict(case_id='case_'+'e'*32,resource_id='resource-2')),
        base.model_copy(update=dict(case_id='case_'+'f'*32)))
    template=HttpRequestTemplate.model_validate_json(json.dumps(dict(method='POST',path='/bulk',
        body=dict(kind='JSON',value={'items':[{'id':{'$slot':'resource'},'value':True}]}),
        input_slots=[dict(slot_id='resource',source='CASE_RESOURCE_ID',consumer='JSON_BODY')])) )
    action=bundle.actions[0].model_copy(update=dict(steps=tuple(step.model_copy(update=dict(request=template)) if step.purpose=='TARGET' else step for step in bundle.actions[0].steps)))
    invocation=ScenarioInvocation.model_validate_json(json.dumps(dict(id='batch',label='逐项读取',batch=dict(strategy='PER_ITEM',
        array_path=['items'],response_items_path='$.items',response_resource_field='resource_id'),items=[dict(id='item-'+str(index),
        permission={name:getattr(case.permission,name) for name in ('intent_id','revision','intent_hash')},
        subject_identity_id=case.subject_test_identity_id,resource_id=case.resource_id) for index,case in enumerate(members)])))
    rows=[dict(resource_id='resource-1',value='first'),dict(resource_id='resource-2',value='second')]
    check_target[1]['batch_response_rows']=rows if response_kind=='complete' else rows[:1] if response_kind=='missing' else [rows[0],rows[0]]
    web=CheckWebRuntime(bundle,environ=environment,cancellation_requested=lambda:False)
    group=dict(invocation=invocation,cases=members,before_others=lambda _actual:None)
    web._batch_groups.update({case.case_id:group for case in members})
    try:
        responses=[web.execute_flow(action,case,verify_identity=True)[1] for case in members]
        assert len(check_target[1]['target_calls'])==1
        assert [item['id'] for item in check_target[1]['batch_payloads'][0]['items']]==['resource-1','resource-2','resource-1']
        assert all(web.target_attempted(case.case_id) for case in members)
        if response_kind=='complete':
            assert [item.data['value'] for item in responses]==['first','second','first']
            assert b'second' not in responses[0].body
        elif response_kind=='missing':
            assert responses[1].batch_item_absent and not responses[0].batch_item_absent
        else:
            assert all(item.data=={} and not item.batch_item_absent for item in responses)
    finally:
        web.close()


pytestmark = [pytest.mark.level4]
