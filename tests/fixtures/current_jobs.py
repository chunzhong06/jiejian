# 当前任务夹具使用真实类型和完整目标字段；无效协议由调用者显式修改 raw 数据构造。
from product.backend.core.lifecycle import JobState
from product.backend.infra.storage import JobRecord


def current_job(*, ordinal: int = 1, target: str = "run_id", operation_type: str = "CHECK", **changes) -> JobRecord:
    prefixes = {"run_id": "run", "recording_id": "rec", "runtime_load_id": "rld", "preflight_id": "ppf"}
    if target not in prefixes:
        raise ValueError("UNKNOWN_JOB_TARGET")
    payload = dict(job_id=f"job_{ordinal:032x}", project_id="fixture-project", operation_type=operation_type,
                   state=JobState.PENDING, idempotency_key=f"fixture-{ordinal}", request_hash="a" * 64,
                   attempt=0, max_attempts=1, available_at_us=1, fencing_token=0, created_at_us=1, updated_at_us=1,
                   **{target: f"{prefixes[target]}_{ordinal:032x}"})
    payload.update(changes)
    return JobRecord.model_validate(payload)


def invalid_job_payload(**changes) -> dict:
    """故意无效的 wire 不伪装成已验证的 JobRecord。"""
    return {**current_job().model_dump(mode="json"), **changes}
