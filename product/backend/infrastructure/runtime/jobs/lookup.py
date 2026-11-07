"""使用调用者的工作单元读取作业；不另开事务或提交状态。"""
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.storage import JobRecord, StorageUnitOfWork


def require_job(work: StorageUnitOfWork, job_id: str) -> JobRecord:
    job = work.jobs.get(job_id)
    if job is None:
        raise JiejianError(ErrorCode.JOB_NOT_FOUND, "任务不存在")
    return job
