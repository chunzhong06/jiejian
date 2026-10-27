# 独立取样目标只关联原授权请求；失败和取消不重放目标，也不产生Run或安全结论。
from product.backend.domain.errors import ErrorCode,JiejianError
from product.protocols.preparation.proof_sources import proof_fingerprint


class ReferenceCaptureTargetHandler:
    def load(self,work,job):
        request=None if job.reference_capture_id is None else work.proof_artifacts.capture(job.project_id,job.reference_capture_id)
        if request is None or job.operation_type!='REFERENCE_CAPTURE' or job.max_attempts!=1 or proof_fingerprint(request)!=job.request_hash:
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT,'取样任务与冻结输入不一致')
        return None,None

    def advance_after_claim(self,work,job,now_us):
        self.load(work,job)
        request=work.proof_artifacts.capture(job.project_id,job.reference_capture_id)
        if not work.proof_artifacts.authorized(request):raise JiejianError(ErrorCode.STATE_PRECONDITION,'取样授权已撤销')
        return None,None

    def finish(self,work,job,now_us,outcome):
        self.load(work,job)
        request=work.proof_artifacts.capture(job.project_id,job.reference_capture_id)
        value=None if request.asset_id is None else work.proof_artifacts.input(job.project_id,request.asset_id)
        if value is not None and value.state=='PENDING':
            state='CANCELLED' if outcome.value=='CANCELLED' else 'INCOMPLETE'
            work.proof_artifacts.update_input(value.model_copy(update={'state':state}),expected_state='PENDING')
        if job.attempt==0 or request.plan.restore is not None:
            work.proof_artifacts.resolve_recovery(job.project_id,request.capture_id,None,now_us)
        return None,None
