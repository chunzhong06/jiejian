# 真实普通Node应用经生产预检查、采用、CHECK Worker/Runner形成权限结论，禁止用接口状态替代业务事实。
from uuid import uuid4
import time
import pytest
from product.backend.workflows.preparation.proofs.commands import SaveProofSource, GrantProofScope, StartProofPreflight, AdoptProofSource
from tests.fixtures.runtime.managed_records import ordinary_application, source_configuration, wait_for


@pytest.mark.parametrize('regression,read_only,expected,source_edits,alternate',[
    (False,False,'PASS',None,False),(True,False,'BLOCK',None,False),(False,True,'PASS',None,False),
    (False,False,'PASS',None,True),(True,False,'BLOCK',None,True),
    (True,False,'BLOCK',{'response.mjs':'export function publicationStatus(allowed) { return 403; }'},False),
    (True,False,'BLOCK',{'response.mjs':'export function publicationStatus(allowed) { return 403; }',
        'transition.mjs':"export function publicationSteps() { return ['publish','withdraw']; }"},False),
    (False,False,'INCONCLUSIVE',{'policy.mjs':'export function mayPublish(actor, ownerId) { return false; }'},False),
])
def test_adopted_json_source_is_consumed_by_formal_check(tmp_path,regression,read_only,expected,source_edits,alternate):
    harness = ordinary_application(tmp_path,regression=regression,read_only=read_only,source_edits=source_edits,alternate=alternate)
    core,project = harness.core,harness.project_id
    service = core.proof_preparation
    try:
        basis = service.context(project)['basis_id']
        saved = service.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=source_configuration(harness)))
        common = dict(source_id=saved['result']['source_id'],revision=1,basis_id=basis)
        service.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common))
        queued = service.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))
        core.worker.start()
        preflight_id = queued['result']['preflight_id']
        report = wait_for(lambda:service.status(project,preflight_id))
        assert report['report']['assessment']=='USABLE',report
        service.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=preflight_id,confirmed=True,**common))
        preview = core.checks.preview(project)
        assert not preview.gaps,preview
        submitted = core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex)
        deadline = time.monotonic()+40
        while time.monotonic()<deadline:
            status = core.check_results.status(submitted.run.run_id,project_id=project)
            if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:
                break
            time.sleep(.1)
        assert status.run.verdict is not None and status.run.verdict.value == expected,status
        boundary = core.business_boundaries.view(project)
        deny = next(item for item in boundary.permission_intents if item.expectation.value==('ALLOW' if read_only else 'DENY'))
        detail = core.rule_details.read(project,deny.intent_id,revision=deny.revision)
        assert detail['preparation_complete'] is True
        assert detail['latest_result']['applies_to_current_implementation'] is True
        assert len(detail['latest_result']['cases'])==1
        if expected!='INCONCLUSIVE':
            assert detail['latest_result']['cases'][0]['verdict']==('VULNERABLE' if regression else 'SAFE')
        assert detail['sentence'].startswith('普通成员对自己' if read_only else '普通成员对负责人')
    finally:
        harness.close()


# 该模块启动真实 Node、Worker 与 Runner，不进入普通 L2。
pytestmark = [pytest.mark.process, pytest.mark.slow]
