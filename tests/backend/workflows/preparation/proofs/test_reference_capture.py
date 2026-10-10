# 普通应用没有已采用证明时仍可正常取样；结果只是候选，采用后才进入原CHECK。
import hashlib
import json
import time
from uuid import uuid4
import pytest
import httpx
from product.backend.core.errors import JiejianError
from product.backend.workflows.preparation.proofs.capture_plan import CaptureSelection
from product.backend.workflows.preparation.proofs.capture_service import StartReferenceCapture,CancelReferenceCapture
from product.backend.workflows.preparation.proofs.artifact_inputs import UploadProofArtifact
from product.backend.workflows.preparation.proofs.commands import SaveProofSource,GrantProofScope,StartProofPreflight,AdoptProofSource
from product.protocols.preparation.proof_sources import FileProofSourceConfig
from tests.fixtures.runtime.managed_records import ordinary_application,source_configuration,wait_for

CONTENT=b'controlled test file content'


def file_source(harness,asset=None):
    config=source_configuration(harness).model_dump(mode='json')
    resource=harness.core.proof_preparation.context(harness.project_id)['resources'][0]
    config.update(source_kind='REFERENCE_FILE',source_contract_id='FILE_RESPONSE_CONTENT_V1',
        reference_artifact=None if asset is None else asset.manifest.model_dump(mode='json'),reference_origin=None if asset is None else asset.origin,
        reference_resource_id=resource['resource_id'],reference_owner_identity_id=resource['owner_identity_id'],
        mappings={'resource_id':['resource_id'],'owner_id':['owner_id']})
    return FileProofSourceConfig.model_validate_json(json.dumps(config))


@pytest.mark.parametrize('origin',['UPLOAD','REFERENCE_CAPTURE'])
def test_prepare_file_and_check_real_delivery(tmp_path,origin):
    harness=ordinary_application(tmp_path,file_delivery=True)
    core,project=harness.core,harness.project_id
    try:
        proofs=core.proof_preparation
        context=proofs.context(project);basis=context['basis_id'];resource=context['resources'][0]
        draft=None
        if origin=='UPLOAD':
            receipt=core.proof_artifacts.upload(project,UploadProofArtifact(operation_id=uuid4().hex,basis_id=basis,
                action_id=harness.action.action_id,action_revision=1,resource_binding_id=resource['resource_binding_id'],
                size=len(CONTENT),sha256=hashlib.sha256(CONTENT).hexdigest(),confirmed=True),CONTENT)
        else:
            draft=proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=file_source(harness)))
            with pytest.raises(JiejianError):
                proofs.start(project,StartProofPreflight(operation_id=uuid4().hex,basis_id=basis,source_id=draft['result']['source_id'],revision=1))
            permission=next(item for item in core.business_boundaries.view(project).permission_intents if item.expectation.value=='ALLOW')
            owner=resource['owner_identity_id']
            selection=CaptureSelection(basis_id=basis,action_id=harness.action.action_id,action_revision=1,
                allow_intent_id=permission.intent_id,resource_binding_id=resource['resource_binding_id'],collection='units',
                identity_claims=tuple(item for item in source_configuration(harness).identity_claims if item.identity_id==owner))
            plan=core.reference_captures.preview(project,selection)
            command=StartReferenceCapture(operation_id=uuid4().hex,basis_id=basis,selection=selection,
                plan_hash=plan.plan_hash,plan_created_at_us=plan.created_at_us,confirmed=True)
            receipt=core.reference_captures.start(project,command)
            assert core.reference_captures.start(project,command)==receipt
            core.worker.start()
            status=wait_for(lambda:core.reference_captures.status(project,receipt['result']['capture_id']))
            assert status['state']=='SUCCEEDED' and status['report']['state']=='CANDIDATE',status
            assert status['report']['recovery_verified'] is True
        with core.uow_factory() as work:
            asset=work.proof_artifacts.input(project,receipt['result']['asset_id'])
        assert asset.state=='COMPLETE' and core.proof_artifacts.read(project,asset.asset_id)==CONTENT
        assert all(not source['adopted'] for source in proofs.context(project)['sources'])
        fields={} if draft is None else dict(source_id=draft['result']['source_id'],expected_revision=1)
        saved=proofs.save(project,SaveProofSource(operation_id=uuid4().hex,basis_id=basis,config=file_source(harness,asset),**fields))
        common=dict(source_id=saved['result']['source_id'],revision=1 if draft is None else 2,basis_id=basis)
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
        assert status.run.verdict is not None and status.run.verdict.value=='PASS',str(status)
    finally:harness.close()


def test_cancel_before_execution_and_restore_failure_without_replaying_target(tmp_path):
    harness=ordinary_application(tmp_path,file_delivery=True,recovery_failures=1)
    core,project=harness.core,harness.project_id
    try:
        context=core.proof_preparation.context(project);resource=context['resources'][0];basis=context['basis_id']
        permission=next(item for item in core.business_boundaries.view(project).permission_intents if item.expectation.value=='ALLOW')
        selection=CaptureSelection(basis_id=basis,action_id=harness.action.action_id,action_revision=1,
            allow_intent_id=permission.intent_id,resource_binding_id=resource['resource_binding_id'],collection='units',
            identity_claims=tuple(item for item in source_configuration(harness).identity_claims if item.identity_id==resource['owner_identity_id']))
        def start(value):
            plan=core.reference_captures.preview(project,value)
            return core.reference_captures.start(project,StartReferenceCapture(operation_id=uuid4().hex,basis_id=basis,
                selection=value,plan_hash=plan.plan_hash,plan_created_at_us=plan.created_at_us,confirmed=True))['result']
        cancelled=start(selection)
        core.reference_captures.cancel(project,CancelReferenceCapture(operation_id=uuid4().hex,basis_id=basis,capture_id=cancelled['capture_id']))
        assert core.reference_captures.status(project,cancelled['capture_id'])['state']=='CANCELLED'
        assert not core.proof_preparation.context(project)['reference_recovery_gaps']
        capture=start(selection);core.worker.start()
        status=wait_for(lambda:core.reference_captures.status(project,capture['capture_id']))
        assert status['state']=='SUCCEEDED' and status['report']['state']=='INCOMPLETE',status
        assert status['report']['target_may_have_run'] and not status['report']['recovery_verified']
        gaps=core.proof_preparation.context(project)['reference_recovery_gaps']
        assert len(gaps)==1 and gaps[0]['reason']=='REFERENCE_RECOVERY_UNVERIFIED'
        preparation=core.preparation.get(project)
        assert not preparation.preparation_complete and preparation.actions[0].resources[0].status.value=='BLOCKED'
        assert core.preparation_guidance.context(project)['guidance']['next_action']['kind']=='REVIEW_REFERENCE_RECOVERY'
        with pytest.raises(JiejianError):core.reference_captures.preview(project,selection)
        restored=start(selection.model_copy(update={'restore_capture_id':capture['capture_id']}))
        assert restored['asset_id'] is None
        result=wait_for(lambda:core.reference_captures.status(project,restored['capture_id']))
        assert result['state']=='SUCCEEDED' and result['report']['state']=='RECOVERED',result
        assert result['report']['restores_capture_id']==capture['capture_id']
        assert not result['report']['target_may_have_run'] and not result['report']['flow_may_have_run']
        assert not core.proof_preparation.context(project)['reference_recovery_gaps']
        with httpx.Client(trust_env=False) as client:
            assert client.get(context['runtime_origin']+'/__test_counts').json()=={'publishCalls':1}
        with core.uow_factory() as work:
            assert work.proof_artifacts.input(project,capture['asset_id']).state=='INCOMPLETE'
    finally:harness.close()


@pytest.mark.parametrize('interruption',['database','cancel'])
def test_sealed_capture_publication_recovers_without_target_and_honors_cancellation(tmp_path,monkeypatch,interruption):
    from product.backend.infra.runtime.jobs.attempts import JobAttempts
    from product.backend.infra.runtime.jobs.models import ClaimJob
    from product.backend.infra.storage.execution.job_control import JobControlRepository
    from product.protocols.preparation.reference_capture import ReferenceCaptureReport
    harness=ordinary_application(tmp_path,file_delivery=True,recovery_failures=1)
    core,project=harness.core,harness.project_id
    try:
        context=core.proof_preparation.context(project);resource=context['resources'][0];basis=context['basis_id']
        permission=next(item for item in core.business_boundaries.view(project).permission_intents if item.expectation.value=='ALLOW')
        selection=CaptureSelection(basis_id=basis,action_id=harness.action.action_id,action_revision=1,
            allow_intent_id=permission.intent_id,resource_binding_id=resource['resource_binding_id'],collection='units',
            identity_claims=tuple(item for item in source_configuration(harness).identity_claims if item.identity_id==resource['owner_identity_id']))
        plan=core.reference_captures.preview(project,selection)
        result=core.reference_captures.start(project,StartReferenceCapture(operation_id=uuid4().hex,basis_id=basis,
            selection=selection,plan_hash=plan.plan_hash,plan_created_at_us=plan.created_at_us,confirmed=True))['result']
        claim=JobAttempts(core.uow_factory).claim(ClaimJob(job_id=result['job_id'],lease_owner='publication-test',
            now_us=time.time_ns()//1000,lease_duration_us=30_000_000)).job
        with core.uow_factory() as work:request=work.proof_artifacts.capture(project,result['capture_id'])
        report=ReferenceCaptureReport(capture_id=request.capture_id,job_id=claim.job_id,fencing_token=claim.fencing_token,
            lease_owner=claim.lease_owner,request_hash=claim.request_hash,plan_hash=plan.plan_hash,authorization_id=request.authorization_id,
            state='INCOMPLETE',target_may_have_run=False,identity_matched=False,resource_matched=False,runtime_matched=True,
            recovery_verified=False,started_at_us=request.created_at_us,completed_at_us=time.time_ns()//1000,
            reason_codes=('IDENTITY_UNAVAILABLE',))
        publisher=core.reference_captures.jobs
        if interruption=='database':
            complete=JobControlRepository.complete_reference_capture
            monkeypatch.setattr(JobControlRepository,'complete_reference_capture',lambda *args,**kwargs:None)
            with pytest.raises(JiejianError):publisher.publish(report)
            assert publisher.reports.publication(request.capture_id)==report
            with core.uow_factory() as work:
                assert work.jobs.get(claim.job_id).state.value=='RUNNING'
                assert work.proof_artifacts.report_hash(project,request.capture_id) is None
            monkeypatch.setattr(JobControlRepository,'complete_reference_capture',complete)
            assert publisher.publish(report,require_active_lease=False)==report
            assert publisher.publish(report)==report
            assert core.reference_captures.status(project,request.capture_id)['state']=='SUCCEEDED'
        else:
            core.reference_captures.cancel(project,CancelReferenceCapture(operation_id=uuid4().hex,basis_id=basis,capture_id=request.capture_id))
            with pytest.raises(JiejianError):publisher.publish(report)
            assert not publisher.reports.publication_path(request.capture_id).exists()
        with httpx.Client(trust_env=False) as client:
            assert client.get(context['runtime_origin']+'/__test_counts').json()=={'publishCalls':0}
    finally:harness.close()


pytestmark=[pytest.mark.process,pytest.mark.slow]
