# =============================================================================
# 通用 Case 编排
#
# 定位
#   Target Runtime Port 与既有 Verification 之间的单 Case 阶段边界。
#
# 职责
#   固定阶段顺序｜保持 TARGET 单次执行｜保证异常进入 cleanup。
#
# 边界
#   不导入 Web、HTTP、Cookie、OAuth、URL、Header 或具体 Observer Adapter。
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.differential import PermissionTwin, TwinExecutionRole
from product.backend.core.verification.facts import ExecutionFact, ObservationFact, SecurityEffectFact
from product.backend.core.verification.permission_coverage import PermissionMutationCase
from product.backend.infra.execution.port import TargetBaselineResult, TargetCaseSession
from product.backend.infra.observers.coordinator import ObserverCoordinator
from product.protocols import ObservationEnvelope, ObservationPhase, ObserverOutcome
from product.protocols.execution import ObserverRequirementBinding


@dataclass(frozen=True, slots=True)
class CaseResult:
    """从 Runtime 事实到 Evidence 之间的不可变 Case 结果。"""

    case: PermissionMutationCase
    execution_fact: ExecutionFact
    verdict: CaseVerdict
    finding_pre_identity: str
    baseline_integrity: bool
    twin_snapshot: PermissionTwin | None = None
    twin_role: TwinExecutionRole | None = None
    allow_control_valid: bool = False
    requirement_bindings: tuple[ObserverRequirementBinding, ...] = ()
    observation_facts: tuple[ObservationFact, ...] = ()
    security_effect_facts: tuple[SecurityEffectFact, ...] = ()
    observations: tuple[ObservationEnvelope, ...] = ()
    outcomes: tuple[ObserverOutcome, ...] = ()
    reason_codes: tuple[str, ...] = ()
    stage_trace: tuple[str, ...] = ()


class CaseOrchestrator:
    """执行一个 Case 的固定阶段，并把目标清理放入 finally。"""

    def __init__(self, *, observers: ObserverCoordinator, bindings, clock, cancellation_requested) -> None:
        self.observers = observers
        self.bindings = bindings
        self.clock = clock
        self.cancellation_requested = cancellation_requested

    def run(self, session: TargetCaseSession, case: PermissionMutationCase, *, action: Any, verify, finding_pre_identity: str, twin: PermissionTwin | None = None, twin_role: TwinExecutionRole | None = None, allow_control_valid: bool = False, baseline_validate=None, baseline_invalid=None) -> Any:
        """运行固定阶段；verify 在 cleanup 前执行既有事实归约与 Verification。"""

        envelopes: list[ObservationEnvelope] = []
        outcomes: dict[str, ObserverOutcome] = {}
        cursors: dict[tuple[str, str], tuple[Any, ...]] = {}
        trace: list[str] = []
        try:
            if self.cancellation_requested():
                raise JiejianError(ErrorCode.EXEC_CANCELLED, "复杂权限执行已取消")
            trace.append("PREPARE")
            session.prepare()
            trace.append("BASELINE")
            baseline_unavailable = self.observers.observe_phase(
                session,
                case,
                ObservationPhase.BASELINE,
                envelopes,
                outcomes,
                cursors,
            )
            baseline = (
                TargetBaselineResult(
                    valid=False,
                    comparison_fingerprints=(),
                    reason_codes=("BASELINE_OBSERVATION_INCOMPLETE",),
                )
                if baseline_unavailable
                else session.evaluate_baseline(
                    tuple(envelopes),
                    ignored_case_fields=(
                        twin.mutation.changed_fields if twin is not None else ()
                    ),
                )
            )
            if baseline_validate is not None:
                # 孪生比较属于 TARGET 前闸门，不能等到事实归约阶段才发现漂移。
                baseline = baseline_validate(baseline)
            if not baseline.valid:
                if baseline_invalid is not None:
                    return baseline_invalid(session, baseline, tuple(envelopes), dict(outcomes))
                raise JiejianError(ErrorCode.BASELINE_INVALID, "目标基线无效")
            trace.append("BEFORE")
            if self.observers.observe_phase(session, case, ObservationPhase.BEFORE, envelopes, outcomes, cursors):
                raise JiejianError(ErrorCode.OBSERVER_INCOMPLETE, "BEFORE 观察不完整")
            trace.append("TARGET")
            execution = session.execute_target()
            trace.append("AFTER")
            self.observers.observe_phase(session, case, ObservationPhase.AFTER, envelopes, outcomes, cursors)
            trace.append("EVENTUAL")
            self.observers.observe_phase(session, case, ObservationPhase.EVENTUAL, envelopes, outcomes, cursors)
            trace.append("RESOLVE")
            execution = session.resolve_execution(tuple(envelopes))
            return verify(session, tuple(envelopes), tuple(outcomes.values()), execution)
        finally:
            trace.append("CLEANUP")
            try:
                session.cleanup()
            except Exception as exc:
                raise JiejianError(ErrorCode.CLEANUP_FAILED, "资源清理失败") from exc
