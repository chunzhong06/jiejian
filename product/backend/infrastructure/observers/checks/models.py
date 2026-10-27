# Runner 内部的观察结果与私有对照投影，不进入公共证据正文。
from dataclasses import dataclass
from product.protocols.checks.check_result import CheckObservation

@dataclass(frozen=True)
class CheckObservedSource:
    observation: CheckObservation
    # 仅在 Runner 内比较受保护业务投影；原始响应/状态不得进入发布文件。
    baseline_projection: tuple | None
    execution_completed: bool = False
    completion_case_id: str | None = None
    completion_resource_id: str | None = None
    completion_binding_fingerprint: str | None = None
