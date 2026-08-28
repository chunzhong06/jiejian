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
from product.backend.core.verification.permissions.coverage import PermissionMutationCase
from product.backend.infra.execution.port import (
    TargetBaselineResult,
    TargetCaseSession,
    TargetCleanupError,
    TargetCleanupIssue,
)
from product.backend.infra.observers.coordinator import ObserverCoordinator
from product.protocols import (
    CleanupIssueCode,
    ObservationEnvelope,
    ObservationPhase,
    ObserverOutcome,
    RunnerFailurePhase,
)
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


class CaseExecutionFailure(Exception):
    """同时保留主执行失败、失败阶段与后置清理问题。"""

    def __init__(
        self,
        primary: Exception,
        phase: RunnerFailurePhase,
        cleanup_issues: tuple[TargetCleanupIssue, ...] = (),
    ) -> None:
        self.primary = primary
        self.phase = phase
        self.cleanup_issues = cleanup_issues
        super().__init__("case execution failed")


class _CaseResultReady(Exception):
    """让 TARGET 前的确定性 INCONCLUSIVE 仍经过统一 cleanup 收敛。"""


class CaseOrchestrator:
    """执行一个 Case 的固定阶段，并把目标清理放入 finally。"""

    def __init__(self, *, observers: ObserverCoordinator, bindings, clock, cancellation_requested, progress=None, progress_clock=None) -> None:
        self.observers = observers
        self.bindings = bindings
        self.clock = clock
        self.cancellation_requested = cancellation_requested
        self.progress = progress
        self.progress_clock = progress_clock or clock

    def run(self, session: TargetCaseSession, case: PermissionMutationCase, *, action: Any, verify, finding_pre_identity: str, twin: PermissionTwin | None = None, twin_role: TwinExecutionRole | None = None, allow_control_valid: bool = False, baseline_validate=None, baseline_invalid=None, requirements_to_run: tuple[str, ...] | None = None) -> Any:
        """运行固定阶段；verify 在 cleanup 前执行既有事实归约与 Verification。"""

        envelopes: list[ObservationEnvelope] = []
        outcomes: dict[str, ObserverOutcome] = {}
        cursors: dict[tuple[str, str], tuple[Any, ...]] = {}
        trace: list[str] = []
        phase = RunnerFailurePhase.TARGET_VALIDATION
        result: Any = None
        primary: Exception | None = None
        cleanup_issues: tuple[TargetCleanupIssue, ...] = ()
        actual_requirements = requirements_to_run or tuple(case.required_observations)
        required_requirements = tuple(case.required_observations)
        required_observer_ids = {
            self.bindings[requirement].observer_id
            for requirement in required_requirements
            if requirement in self.bindings
        }

        def observe_phase(phase: ObservationPhase) -> bool:
            args = (
                session,
                case,
                phase,
                envelopes,
                outcomes,
                cursors,
            )
            if actual_requirements == required_requirements:
                return self.observers.observe_phase(*args)
            return self.observers.observe_phase(
                *args,
                requirements_to_run=actual_requirements,
                required_requirements=required_requirements,
            )

        def progress_event(phase_name: str, state: str) -> None:
            try:
                if self.progress is not None:
                    self.progress.record(
                        case_id=case.case_id,
                        action_id=case.action_id,
                        twin_role=twin_role.value if twin_role is not None else None,
                        phase=phase_name,
                        state=state,
                        recorded_at_us=max(int(self.progress_clock()), 0),
                    )
            except Exception:
                # 进度旁路不得改变执行、清理或安全结论。
                return

        try:
            if self.cancellation_requested():
                raise JiejianError(ErrorCode.EXEC_CANCELLED, "复杂权限执行已取消")
            trace.append("PREPARE")
            phase = RunnerFailurePhase.PREPARE_RECOVERY
            progress_event("PREPARE", "STARTED")
            session.prepare()
            progress_event("PREPARE", "COMPLETED")
            trace.append("BASELINE")
            phase = RunnerFailurePhase.BASELINE
            progress_event("BASELINE", "STARTED")
            baseline_unavailable = observe_phase(ObservationPhase.BASELINE)
            baseline = (
                TargetBaselineResult(
                    valid=False,
                    comparison_fingerprints=(),
                    reason_codes=("BASELINE_OBSERVATION_INCOMPLETE",),
                )
                if baseline_unavailable
                else session.evaluate_baseline(
                    tuple(
                        item
                        for item in envelopes
                        if not required_observer_ids
                        or item.observer_id in required_observer_ids
                    ),
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
                    result = baseline_invalid(
                        session,
                        baseline,
                        tuple(envelopes),
                        dict(outcomes),
                    )
                    raise _CaseResultReady
                raise JiejianError(ErrorCode.BASELINE_INVALID, "目标基线无效")
            trace.append("BEFORE")
            phase = RunnerFailurePhase.BEFORE
            if observe_phase(ObservationPhase.BEFORE):
                raise JiejianError(ErrorCode.OBSERVER_INCOMPLETE, "BEFORE 观察不完整")
            progress_event("BASELINE", "COMPLETED")
            trace.append("TARGET")
            phase = RunnerFailurePhase.TARGET
            progress_event("TARGET", "STARTED")
            execution = session.execute_target()
            progress_event("TARGET", "COMPLETED")
            trace.append("AFTER")
            phase = RunnerFailurePhase.AFTER
            progress_event("OBSERVE", "STARTED")
            observe_phase(ObservationPhase.AFTER)
            trace.append("EVENTUAL")
            phase = RunnerFailurePhase.EVENTUAL
            observe_phase(ObservationPhase.EVENTUAL)
            trace.append("RESOLVE")
            phase = RunnerFailurePhase.VERIFY
            execution = session.resolve_execution(tuple(envelopes))
            progress_event("OBSERVE", "COMPLETED")
            progress_event("VERIFY", "STARTED")
            result = verify(
                session,
                tuple(envelopes),
                tuple(outcomes.values()),
                execution,
            )
            progress_event("VERIFY", "COMPLETED")
        except _CaseResultReady:
            pass
        except Exception as exc:
            primary = exc
        finally:
            trace.append("CLEANUP")
            progress_event("RECOVERY", "STARTED")
            try:
                session.cleanup()
                progress_event("RECOVERY", "COMPLETED")
            except TargetCleanupError as exc:
                cleanup_issues = exc.issues
            except Exception as exc:
                cleanup_issues = (
                    TargetCleanupIssue(
                        CleanupIssueCode.POST_CASE_RECOVERY_FAILED,
                        exc.code if isinstance(exc, JiejianError) else None,
                    ),
                )
        if primary is None and cleanup_issues:
            primary = JiejianError(ErrorCode.CLEANUP_FAILED, "资源清理失败")
            phase = RunnerFailurePhase.POST_CASE_RECOVERY
        if primary is not None:
            phase = _specific_failure_phase(primary, phase)
            raise CaseExecutionFailure(primary, phase, cleanup_issues) from primary
        return result


def _specific_failure_phase(
    error: Exception,
    fallback: RunnerFailurePhase,
) -> RunnerFailurePhase:
    """细分 PREPARE 内失败，同时保留其他阶段已经确定的现场。"""

    if not isinstance(error, JiejianError):
        return fallback
    if error.code == ErrorCode.VALUE_EXTRACTION_FAILED.value:
        return (
            RunnerFailurePhase.SETUP
            if fallback is RunnerFailurePhase.PREPARE_RECOVERY
            else fallback
        )
    return {
        ErrorCode.PREPARE_RECOVERY_FAILED.value: RunnerFailurePhase.PREPARE_RECOVERY,
        ErrorCode.IDENTITY_PREPARATION_FAILED.value: RunnerFailurePhase.IDENTITY_PREPARATION,
        ErrorCode.SETUP_STEP_FAILED.value: RunnerFailurePhase.SETUP,
        ErrorCode.SELF_TARGET_FORBIDDEN.value: RunnerFailurePhase.TARGET_VALIDATION,
    }.get(error.code, fallback)
