# 加载任务复用租约与取消，不能被CHECK误领；发布失败不留下启动成功或安全结论。
from functools import partial
from uuid import uuid4

import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.runtime.jobs.attempts import JobAttempts
from product.backend.infra.runtime.jobs.models import ClaimJob, RequestCancellation
from product.backend.infra.runtime.jobs.queue import JobQueue
from product.backend.infra.runtime.jobs.target_handlers.runtime_load import runtime_load_targets
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.runtime.load_jobs import RuntimeLoadJobs
from product.protocols.runtime.node_runtime import NodeRuntimeLoadRequest, NodeRuntimeLoadReceipt, NodeRuntimeReference, node_document_fingerprint

NOW = 1_790_000_000_000_000


def _services(worker_services):
    factory=partial(StorageUnitOfWork,worker_services.session_factory)
    targets=runtime_load_targets()
    return factory,RuntimeLoadJobs(factory),JobAttempts(factory,targets=targets),JobQueue(factory,targets=targets)


def _request():
    return NodeRuntimeLoadRequest(load_id='rld_'+uuid4().hex,project_id='job-runtime-project',
        operation_id=uuid4().hex,control_session_id='rcs_'+'4'*32,preview_fingerprint='c'*64,instance_id='rti_'+uuid4().hex,manifest_fingerprint='a'*64,
        source_fingerprint='b'*64,created_at_us=NOW)


def _receipt(request):
    return NodeRuntimeLoadReceipt(load_id=request.load_id,request_fingerprint=node_document_fingerprint(request),
        reference=NodeRuntimeReference(project_id=request.project_id,instance_id=request.instance_id,
            manifest_fingerprint=request.manifest_fingerprint,source_fingerprint=request.source_fingerprint,
            process_id=123,process_created_at=456,port=19273),started_at_us=NOW+30)


def test_runtime_submission_replays_and_default_check_worker_cannot_claim(worker_services):
    factory,service,attempts,_=_services(worker_services)
    request=_request();first=service.submit(request)
    assert service.submit(request)==first
    with pytest.raises(JiejianError):
        service.submit(request.model_copy(update={'instance_id':'rti_'+'3'*32}))
    assert worker_services.attempts.claim(ClaimJob(lease_owner='check-worker',now_us=NOW+10,lease_duration_us=1000)) is None
    claimed=attempts.claim(ClaimJob(job_id=first['job'].job_id,lease_owner='runtime-worker',now_us=NOW+10,lease_duration_us=1000))
    assert claimed.run is None and claimed.recording is None
    assert claimed.job.runtime_load_id==request.load_id
    with factory() as work:
        assert work.runs.list_for_project(request.project_id)==()
    assert service.operation('other-project',request.operation_id) is None


def test_runtime_publication_is_atomic_and_rejects_old_fence(worker_services,monkeypatch):
    factory,service,attempts,_=_services(worker_services)
    request=_request();job=service.submit(request)['job']
    claim=attempts.claim(ClaimJob(job_id=job.job_id,lease_owner='runtime-worker',now_us=NOW+10,lease_duration_us=1000))
    receipt=_receipt(request)
    arguments=dict(job_id=job.job_id,attempt=1,lease_owner='runtime-worker',fencing_token=claim.job.fencing_token,receipt=receipt)
    with pytest.raises(JiejianError): service.publish(**(arguments|{'fencing_token':claim.job.fencing_token+1}))
    from product.backend.infra.storage.runtime.runtime_loads import RuntimeLoadRepository
    publish=RuntimeLoadRepository.publish
    def fail(self,value): raise RuntimeError('injected receipt failure')
    monkeypatch.setattr(RuntimeLoadRepository,'publish',fail)
    with pytest.raises(RuntimeError): service.publish(**arguments)
    with factory() as work:
        assert work.jobs.get(job.job_id).state is JobState.RUNNING
        assert work.runtime_loads.receipt(request.load_id) is None
    monkeypatch.setattr(RuntimeLoadRepository,'publish',publish)
    assert service.publish(**arguments)==receipt
    assert service.publish(**arguments)==receipt
    restored=RuntimeLoadJobs(factory).operation(request.project_id,request.operation_id)
    assert restored['job'].state is JobState.SUCCEEDED
    assert restored['receipt']==receipt


def test_cancelled_runtime_attempt_cannot_publish_success(worker_services):
    _,service,attempts,queue=_services(worker_services)
    request=_request();job=service.submit(request)['job']
    claim=attempts.claim(ClaimJob(job_id=job.job_id,lease_owner='runtime-worker',now_us=NOW+10,lease_duration_us=1000))
    queue.request_cancellation(RequestCancellation(job_id=job.job_id,now_us=NOW+20))
    with pytest.raises(JiejianError):
        service.publish(job_id=job.job_id,attempt=1,lease_owner='runtime-worker',fencing_token=claim.job.fencing_token,receipt=_receipt(request))
    assert service.operation(request.project_id,request.operation_id)['receipt'] is None
