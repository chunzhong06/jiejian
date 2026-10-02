# 原子提交独立预检查并发布有fence的报告引用；预检查成功不生成安全结论或正式采用。
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState
from product.backend.infra.storage import JobRecord
from product.backend.infra.artifacts.proof_reports import ProofReportStore
from product.backend.infra.runtime.jobs.events import append_job_event
from product.backend.infra.runtime.jobs.models import JobEventType
from product.protocols.proof_sources import proof_fingerprint


class ProofPreflightJobs:
    def __init__(self, var_dir, uow_factory):
        self._uow = uow_factory
        self.store = ProofReportStore(var_dir)

    def submit(self, work, request, *, operation_id):
        """调用者先检查当前授权，并将操作回执一起提交，未知响应仅回读原键。"""
        work.proof_sources.add_preflight(request)
        job = JobRecord(job_id='job_' + uuid4().hex, project_id=request.project_id,
            preflight_id=request.preflight_id, operation_type='PROOF_PREFLIGHT', state=JobState.PENDING,
            idempotency_key=operation_id, request_hash=proof_fingerprint(request), attempt=0, max_attempts=1,
            available_at_us=request.created_at_us, fencing_token=0,
            created_at_us=request.created_at_us, updated_at_us=request.created_at_us)
        work.jobs.add(job)
        append_job_event(work, job=job, event_type=JobEventType.JOB_SUBMITTED, source_state=None,
            target_state=JobState.PENDING, occurred_at_us=request.created_at_us, metadata={'operation_type':'PROOF_PREFLIGHT'})
        return job

    def publish(self, report, *, known_secrets=()):
        digest = self.store.save(report, known_secrets=known_secrets)
        with self._uow() as work:
            work.acquire_write_lock()
            job = work.jobs.get(report.job_id)
            request = None if job is None else work.proof_sources.preflight(job.project_id, report.preflight_id)
            if (request is None or job.preflight_id != report.preflight_id
                    or proof_fingerprint(request) != report.request_fingerprint
                    or request.source_fingerprint != report.source_fingerprint
                    or work.proof_sources.scope(request.project_id, request.scope.scope_id) != request.scope):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '预检查输入或读取授权已失效')
            if report.assessment == 'USABLE':
                from collections import Counter
                from product.protocols.proof_sources import ManagedProofSourceConfig
                if not isinstance(request.config,ManagedProofSourceConfig) or request.contract is None or request.contract.implementation_profile!='CONTROLLED_TRANSACTION_RECORDS_V1':
                    raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID,'来源没有当前支持的完整证明依据')
                required = Counter({('MAPPING_READABLE',key):1 for key in request.config.mappings})
                required.update({('ACTUAL_IDENTITY_MATCH',None):len(request.identities),
                    ('RESOURCE_OWNER_MATCH',None):1,('SOURCE_CONTRACT_VERIFIED',None):1})
                if request.config.protected_projection:
                    required[('PROTECTED_FIELD_READABLE',None)] = len(request.config.protected_projection)
                if request.contract is None or Counter((item.code,item.mapping_key) for item in report.checks) != required:
                    raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID,'预检查报告缺少必须核对的项目')
            if job.state is JobState.SUCCEEDED and work.proof_sources.report_hash(job.project_id, report.preflight_id) == digest:
                return report
            now = __import__('time').time_ns() // 1000
            if not request.created_at_us <= report.started_at_us <= report.completed_at_us <= now:
                raise JiejianError(ErrorCode.RUNNER_PROTOCOL_INVALID,'预检查报告时间关联无效')
            completed = work.job_control.complete_preflight(job_id=job.job_id, preflight_id=request.preflight_id,
                request_hash=report.request_fingerprint, attempt=report.attempt, lease_owner=report.lease_owner,
                fencing_token=report.fencing_token, now_us=now)
            if completed is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, '预检查已取消、过期或不再属于当前执行者')
            work.proof_sources.publish(job.project_id, request.preflight_id, digest)
            append_job_event(work, job=completed, event_type=JobEventType.JOB_SUCCEEDED,
                source_state=JobState.RUNNING, target_state=JobState.SUCCEEDED, occurred_at_us=now,
                metadata={'attempt':report.attempt, 'fencing_token':report.fencing_token})
            work.commit()
        return report

    def read(self, work, project_id, preflight_id):
        request = work.proof_sources.preflight(project_id, preflight_id)
        if request is None:
            raise JiejianError(ErrorCode.RECORD_NOT_FOUND, '预检查不存在')
        job = work.jobs.get_by_preflight(preflight_id)
        digest = work.proof_sources.report_hash(project_id, preflight_id)
        report = None if digest is None else self.store.read(digest)
        if (job is None or job.request_hash != proof_fingerprint(request)
                or (job.state is JobState.SUCCEEDED) != (report is not None)
                or (report is not None and (report.job_id, report.preflight_id, report.request_fingerprint,
                    report.source_fingerprint, report.attempt, report.fencing_token) !=
                    (job.job_id, preflight_id, job.request_hash, request.source_fingerprint, job.attempt, job.fencing_token))):
            raise JiejianError(ErrorCode.STORAGE_STATE, '预检查输入、任务或报告关联不一致')
        return request, job, report
