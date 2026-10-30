# 显式装配当前任务目标，目标协议与处理器不反向导入此装配模块。
from product.backend.infrastructure.runtime.jobs.targets import (
    JobTargetRegistry, JobTargetType, CheckJobTargetHandler,
    ProofPreflightTargetHandler, ReferenceCaptureTargetHandler, RuntimeLoadTargetHandler, IdentityPreparationTargetHandler,
)

def recording_job_targets() -> JobTargetRegistry:
    """构造当前录制能力；不隐式登记检查或其他后台任务。"""
    from product.backend.infrastructure.runtime.jobs.recording import RecordingJobTargetHandler

    registry = JobTargetRegistry()
    registry.register(JobTargetType.RECORDING, RecordingJobTargetHandler())
    return registry

def current_check_and_recording_targets() -> JobTargetRegistry:
    """装配短期检查、录制和预检查；长驻运行加载由独立监督器领取。"""
    from product.backend.infrastructure.runtime.jobs.recording import RecordingJobTargetHandler

    registry = JobTargetRegistry()
    registry.register(JobTargetType.RUN, CheckJobTargetHandler())
    registry.register(JobTargetType.RECORDING, RecordingJobTargetHandler())
    registry.register(JobTargetType.PROOF_PREFLIGHT, ProofPreflightTargetHandler())
    registry.register(JobTargetType.REFERENCE_CAPTURE,ReferenceCaptureTargetHandler())
    registry.register(JobTargetType.IDENTITY_PREPARATION, IdentityPreparationTargetHandler())
    return registry


def runtime_load_targets() -> JobTargetRegistry:
    registry = JobTargetRegistry()
    registry.register(JobTargetType.RUNTIME_LOAD, RuntimeLoadTargetHandler())
    return registry
