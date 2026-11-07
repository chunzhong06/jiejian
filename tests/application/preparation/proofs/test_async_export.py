"""普通 Node 导出应用走候选、授权、预检、采用、检查和发布，不由任务成功代替文件证据。"""
import hashlib
import json
import time
from uuid import uuid4

import pytest
from product.backend.application.preparation.proofs.artifact_inputs import UploadProofArtifact
from product.backend.application.preparation.proofs.commands import SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource
from product.protocols.preparation.proof_sources import FileProofSourceConfig,AsyncExportMapping
from tests.support.builders.runtime.managed_records import ordinary_application,source_configuration,wait_for,reload_ordinary_policy

CONTENT=b'controlled test file content'


def export_mapping():
    return AsyncExportMapping(dispatch_task_path=('export_job',),status_path_template='/exports/{task_id}',
        file_path_template='/exports/{task_id}/content',task_path=('job',),state_path=('state',),resource_path=('resource',),
        owner_path=('owner',),subject_path=('subject',),request_nonce_path=('nonce',),
        states={'queued':'QUEUED','done':'SUCCESS','failed':'FAILED','cancelled':'CANCELLED'},
        max_polls=8,poll_interval_us=10_000,timeout_us=1_500_000)


@pytest.mark.parametrize('mode,regression,expected',[('SUCCESS',False,'PASS'),('SUCCESS',True,'BLOCK'),('ID_ONLY',False,'INCONCLUSIVE'),('FAILED',False,'INCONCLUSIVE'),
    ('TRUNCATED',False,'INCONCLUSIVE'),('UNRELATED',False,'INCONCLUSIVE'),('CANCELLED',False,'INCONCLUSIVE')])
def test_ordinary_export_requires_correlated_terminal_and_full_entity(tmp_path,mode,regression,expected):
    harness=ordinary_application(tmp_path,file_delivery=True,async_export=mode,regression=regression)
    core,project=harness.core,harness.project_id
    try:
        proofs=core.proof_preparation
        context=proofs.context(project);basis=context['basis_id'];resource=context['resources'][0]
        uploaded=core.proof_artifacts.upload(project,UploadProofArtifact(operation_id=uuid4().hex,basis_id=basis,
            action_id=harness.action.action_id,action_revision=1,resource_binding_id=resource['resource_binding_id'],
            size=len(CONTENT),sha256=hashlib.sha256(CONTENT).hexdigest(),confirmed=True),CONTENT)
        asset=next(item for item in proofs.context(project)['reference_inputs'] if item['asset_id']==uploaded['result']['asset_id'])
        config=source_configuration(harness).model_dump(mode='json')
        config.update(source_kind='REFERENCE_FILE',source_contract_id='FILE_RESPONSE_CONTENT_V1',
            mappings={'resource_id':['resource_id'],'owner_id':['owner_id']},reference_artifact=asset['manifest'],
            reference_origin='UPLOAD',reference_resource_id=resource['resource_id'],reference_owner_identity_id=resource['owner_identity_id'],
            async_export=export_mapping().model_dump(mode='json'))
        config=FileProofSourceConfig.model_validate_json(json.dumps(config))
        saved=proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=config))
        common=dict(basis_id=basis,source_id=saved['result']['source_id'],revision=1)
        proofs.grant_scope(project,GrantProofScope(operation_id=uuid4().hex,confirmed=True,**common))
        queued=proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,**common));core.worker.start()
        report=wait_for(lambda:proofs.status(project,queued['result']['preflight_id']))
        assert report['report']['assessment']=='USABLE',report
        proofs.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
        preview=core.checks.preview(project)
        assert preview.can_execute,preview
        submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex)
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            status=core.check_results.status(submitted.run.run_id,project_id=project)
            if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
            time.sleep(.1)
        assert status.run.verdict is not None and status.run.verdict.value==expected,str(status)
        package=core.check_results.package(submitted.run.run_id,project_id=project)
        for evidence in package.evidence:
            index=core.check_results.evidence_records(submitted.run.run_id,evidence.evidence_id,evidence.case.case_id,project_id=project)
            task_ids={fact.fact_id for fact in evidence.business_facts if fact.data.kind=='ASYNC_TASK'}
            for record in index.records:
                if record.record_id in task_ids:
                    view=core.check_results.evidence_records(submitted.run.run_id,evidence.evidence_id,evidence.case.case_id,project_id=project,record_id=record.record_id)
                    assert view.role=='SUPPORTING' and view.values
        if mode=='SUCCESS' and regression:
            original=package.result.run_id
            reference=core.check_repairs.contracts(original)[0].reference()
            for policy,expected_repair in [('true /* ineffective correction */','BLOCK'),("actor.role === 'owner' && actor.id === ownerId",'PASS')]:
                change=reload_ordinary_policy(harness,policy,repair_reference=reference)
                common={**common,'basis_id':proofs.context(project)['basis_id']}
                queued=proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,**common))
                report=wait_for(lambda:proofs.status(project,queued['result']['preflight_id']))
                assert report['report']['assessment']=='USABLE',report
                proofs.adopt(project,AdoptProofSource(operation_id=uuid4().hex,preflight_id=queued['result']['preflight_id'],confirmed=True,**common))
                preview=core.checks.preview(project,change_id=change)
                assert preview.can_execute,preview.gaps
                submitted=core.checks.submit(project,expected_plan_fingerprint=preview.plan_fingerprint,idempotency_key=uuid4().hex,change_id=change)
                deadline=time.monotonic()+45
                while time.monotonic()<deadline:
                    status=core.check_results.status(submitted.run.run_id,project_id=project)
                    if status.run.lifecycle.value in {'COMPLETED','FAILED','CANCELLED','SAFETY_STOPPED'}:break
                    time.sleep(.1)
                repeated=core.check_results.package(submitted.run.run_id,project_id=project)
                assert repeated.result.verdict.value==expected_repair,[(item.verdict,item.reason_codes) for item in repeated.result.case_results]
                review=core.check_story.build(submitted.run.run_id).repair_verification
                assert review.status==('VERIFIED' if expected_repair=='PASS' else 'NOT_VERIFIED'),review
                assert review.source_run_id==original
                assert core.check_results.package(original,project_id=project).result.verdict.value=='BLOCK'

    finally:harness.close()


pytestmark=pytest.mark.level4
