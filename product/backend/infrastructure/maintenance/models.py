# 固定维护计划与候选身份，仅在服务端保存真实路径。
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class MaintenanceCandidate:
    """冻结一次预览中的候选身份；真实路径只留在服务端当前实例。"""

    item_id: str
    label: str
    relative_path: str
    path: Path
    root: Path
    estimated_bytes: int
    fingerprint: str
    category: str = "temporary"


@dataclass(frozen=True)
class MaintenancePlan:
    """把普通维护预览冻结为一次短期、单实例、一次性确认计划。"""

    plan_id: str
    scope: str
    generated_at_us: int
    expires_at_us: int
    candidates: tuple[MaintenanceCandidate, ...]
