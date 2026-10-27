# 保存TARGET前的受控资源摘要；恢复只核对原Job/attempt/request，缺失起点不能猜测已恢复。
import hashlib
import os
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.infrastructure.artifacts.checks.check_packages import read_check_bytes,reject_check_links
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.protocols.preparation.reference_capture import ReferenceCaptureBaseline,CaptureRecoveryReference
from product.protocols.preparation.proof_sources import proof_bytes


def save_capture_baseline(directory,value):
    raw=proof_bytes(value)
    temporary=directory/'capture-baseline.tmp';destination=directory/'capture-baseline.json'
    reject_check_links(directory,temporary);reject_check_links(directory,destination)
    with temporary.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.link(temporary,destination);temporary.unlink()


def read_capture_baseline(var_dir,work,project_id,capture_id):
    request=work.proof_artifacts.capture(project_id,capture_id)
    job=work.jobs.get_by_capture(capture_id)
    if request is None or request.plan.restore is not None or job is None or job.project_id!=project_id or job.attempt!=1:
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'原取样没有可核对的恢复起点',details={'reason':'REFERENCE_BASELINE_UNAVAILABLE'})
    path=RuntimePaths(var_dir).jobs/job.job_id/'attempts'/f'{job.attempt}-{job.fencing_token}'/'capture-baseline.json'
    reject_check_links(RuntimePaths(var_dir).jobs,path)
    try:
        raw=read_check_bytes(path);baseline=ReferenceCaptureBaseline.model_validate_json(raw,strict=True)
        if proof_bytes(baseline)!=raw or (baseline.capture_id,baseline.job_id,baseline.attempt,baseline.fencing_token,baseline.request_hash,
            baseline.resource_id,baseline.owner_identity_id,baseline.collection)!=(capture_id,job.job_id,job.attempt,job.fencing_token,job.request_hash,
                request.plan.case.resource_id,request.plan.case.resource_owner_test_identity_id,request.plan.resource_source.collection):
            raise ValueError('baseline association')
        if baseline.observed_at_us<request.created_at_us:raise ValueError('baseline time')
    except (JiejianError,ValueError):
        raise JiejianError(ErrorCode.STATE_PRECONDITION,'原恢复起点缺失或无法核对。请准备独立的新测试资源，旧记录保留为恢复未确认。',details={'reason':'REFERENCE_BASELINE_UNAVAILABLE'}) from None
    return CaptureRecoveryReference(capture_id=capture_id,request_hash=job.request_hash,baseline_document_sha256=hashlib.sha256(raw).hexdigest(),
        baseline_sha256=baseline.baseline_sha256,generation=baseline.generation,resource_id=baseline.resource_id,owner_identity_id=baseline.owner_identity_id,collection=baseline.collection)
