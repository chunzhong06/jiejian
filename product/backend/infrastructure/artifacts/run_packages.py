# 当前录制共享的 attempt 路径与工件定位。
from dataclasses import dataclass
from pathlib import Path
from product.backend.domain.errors import ErrorCode,JiejianError
from product.backend.infrastructure.storage import JobRecord
from product.backend.infrastructure.runtime.paths import RuntimePaths

@dataclass(frozen=True, slots=True)
class AttemptPaths:
    attempt_dir: Path
    input_path: Path
    cancel_path: Path
    staging_dir: Path
    result_path: Path
    receipt_path: Path


def attempt_paths_for(var_dir: Path, job: JobRecord) -> AttemptPaths:
    """以受约束 Job ID、attempt 和 token 唯一定位当前尝试。"""

    jobs_root = RuntimePaths(var_dir).jobs.resolve()
    attempt_dir = (
        jobs_root / job.job_id / "attempts" / f"{job.attempt}-{job.fencing_token}"
    ).resolve()
    if not attempt_dir.is_relative_to(jobs_root):
        raise JiejianError(ErrorCode.RUNNER_START_FAILED, "Runner 尝试路径越界")
    staging = attempt_dir / "staging"
    return AttemptPaths(
        attempt_dir=attempt_dir,
        input_path=attempt_dir / "input.json",
        cancel_path=attempt_dir / "cancel.requested",
        staging_dir=staging,
        result_path=staging / "result.json",
        receipt_path=attempt_dir / "trusted-result.json",
    )
