# 独立预检查目标只核对冻结读取输入，不创建安全Run或修改正式证明绑定。
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.jobs.targets import JobTargetRegistry, JobTargetType
from product.protocols.proof_sources import proof_fingerprint


class ProofPreflightTargetHandler:
    def load(self, work, job):
        request = None if job.preflight_id is None else work.proof_sources.preflight(job.project_id, job.preflight_id)
        if (request is None or job.operation_type != "PROOF_PREFLIGHT"
                or proof_fingerprint(request) != job.request_hash):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "预检查Job与冻结输入不一致")
        return None, None

    def advance_after_claim(self, work, job, now_us):
        return self.load(work, job)

    def finish(self, work, job, now_us, outcome):
        return self.load(work, job)


def proof_preflight_targets():
    registry = JobTargetRegistry()
    registry.register(JobTargetType.PROOF_PREFLIGHT, ProofPreflightTargetHandler())
    return registry
