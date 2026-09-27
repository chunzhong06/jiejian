# 跨应用验收的观察数据与稳定失败类型。
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import ObservedEffect



_VERDICT = {
    CaseVerdict.VULNERABLE: "BLOCK",
    CaseVerdict.SAFE: "PASS",
    CaseVerdict.INCONCLUSIVE: "INCONCLUSIVE",
}


OFFICIAL_PROJECT_ID = "campus-digital-museum"


OFFICIAL_RESOURCE_ID = "campus-digital-museum-package"


class ValidationSuiteError(RuntimeError):
    """只承载无 oracle 正文的稳定 suite 失败码。"""


@dataclass(frozen=True, slots=True)
class _ExecutionObservation:
    allow_status: int
    allow_effect: ObservedEffect
    allow_trace: tuple[Mapping[str, object], ...]
    allow_trace_complete: bool
    deny_status: int
    deny_effect: ObservedEffect
    deny_trace: tuple[Mapping[str, object], ...]
    deny_trace_complete: bool
    actual_identity_attributed: bool
    recovery_success: bool
