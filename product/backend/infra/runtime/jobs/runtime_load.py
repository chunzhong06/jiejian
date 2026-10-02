# 运行加载复用Job的租约/取消/恢复，不创建Run或复制另一套任务生命周期。
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.jobs.targets import JobTargetRegistry, JobTargetType
from product.protocols.node_runtime import node_document_fingerprint


class RuntimeLoadTargetHandler:
    def load(self, work, job):
        request = None if job.runtime_load_id is None else work.runtime_loads.get(job.runtime_load_id)
        if (request is None or job.run_id is not None or job.recording_id is not None
                or job.operation_type != "RUNTIME_LOAD" or request.project_id != job.project_id
                or node_document_fingerprint(request) != job.request_hash):
            raise JiejianError(ErrorCode.JOB_REQUEST_CONFLICT, "运行加载Job与冻结输入不一致")
        # 输入与回执由runtime_loads持久保存；Run/Recording字段保持为空。
        return None, None

    def advance_after_claim(self, work, job, now_us):
        return self.load(work, job)

    def finish(self, work, job, now_us, outcome):
        return self.load(work, job)


def runtime_load_targets():
    registry = JobTargetRegistry()
    registry.register(JobTargetType.RUNTIME_LOAD, RuntimeLoadTargetHandler())
    return registry
