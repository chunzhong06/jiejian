# =============================================================================
# 通用 Runner Executor
#
# 定位
#   以 Target Runtime Port 驱动 CaseOrchestrator，并把纯事实交给既有
#   Verification；具体 Web 注册只存在于 composition。
#
# 边界
#   不导入 Web、HTTP、Cookie、OAuth、URL、Header、JSONPath 或具体 Adapter。
# =============================================================================

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.differential import PermissionTwin, TwinExecutionRole
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, ObservedEffect, TemporalClosure, aggregate_security_effect
from product.backend.core.verification.permissions.evaluation import CaseDecisionInput, evaluate_permission_case
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.infra.execution.port import TargetBaselineResult, TargetRuntime, TargetRuntimeContext, TargetRuntimeFactory
from product.backend.infra.observers.coordinator import ObserverCoordinator, default_observer_registry
from product.backend.infra.runtime.runner.case_orchestrator import CaseOrchestrator, CaseResult
from product.protocols import ObservationEnvelope, ObserverOutcome, ObserverOutcomeStatus, RunnerInput


def _validate_twin_baseline(
    baselines: dict[str, tuple[str, ...]],
    twin: PermissionTwin | None,
    twin_role: TwinExecutionRole | None,
    baseline: TargetBaselineResult,
) -> TargetBaselineResult:
    """冻结 ALLOW 基线，并在 TARGET 前拒绝不一致的 DENY 基线。"""

    if not baseline.valid or twin is None or twin_role is None:
        return baseline
    if twin_role is TwinExecutionRole.ALLOW_CONTROL:
        baselines[twin.twin_id] = baseline.comparison_fingerprints
        return baseline
    if baselines.get(twin.twin_id) == baseline.comparison_fingerprints:
        return baseline
    return TargetBaselineResult(
        valid=False,
        comparison_fingerprints=baseline.comparison_fingerprints,
        reason_codes=("TWIN_BASELINE_MISMATCH",),
    )


def _requirements_to_run(case, action, effect_bindings: Mapping[str, object]) -> tuple[str, ...]:
    """按 Action 效果声明稳定合并关键与佐证观察来源。"""

    requirements: list[str] = []
    required: list[str] = []
    supporting: list[str] = []
    for effect_id in action.effect_ids:
        binding = effect_bindings[effect_id]
        for requirement_id in (*binding.required_channels, *binding.corroborating_channels):
            if requirement_id not in requirements:
                requirements.append(requirement_id)
        required.extend(binding.required_channels)
        supporting.extend(binding.corroborating_channels)
    if set(required) != set(case.required_observations) or set(required) & set(supporting):
        raise JiejianError(ErrorCode.EXECUTION_PROFILE_INVALID, "执行快照观察绑定不一致")
    return tuple(requirements)


def _apply_required_observer_guard(
    case,
    bindings,
    outcomes: tuple[ObserverOutcome, ...],
    effects,
    verdict: CaseVerdict,
    reasons: tuple[str, ...],
) -> tuple[CaseVerdict, tuple[str, ...]]:
    """证据不足默认降级；仅保留已由闭合权威效果事实证明的漏洞。"""

    required_observer_ids = {
        bindings[item].observer_id for item in case.required_observations
    }
    required_unavailable = any(
        item.observer_id in required_observer_ids
        and item.status is not ObserverOutcomeStatus.AVAILABLE
        for item in outcomes
    )
    authoritative_confirmed = any(
        item.state is ObservedEffect.CONFIRMED
        and item.complete
        and item.reliable
        and item.correlated
        and item.temporal_closure is TemporalClosure.CLOSED
        and item.baseline_integrity
        for item in effects
    )
    if required_unavailable and not (
        verdict is CaseVerdict.VULNERABLE and authoritative_confirmed
    ):
        return CaseVerdict.INCONCLUSIVE, tuple(
            sorted(set((*reasons, "REQUIRED_OBSERVER_INCOMPLETE")))
        )
    return verdict, reasons


class RunnerExecutor:
    """跨 Target 的 attempt 内 Case 执行器；不持有任何 Web 专属状态。"""

    def __init__(self, document: RunnerInput, *, runtime_factory: TargetRuntimeFactory, environ: Mapping[str, str], staging: Path, clock: Callable[[], int], cancellation_requested: Callable[[], bool] | None = None, progress=None, progress_clock: Callable[[], int] | None = None) -> None:
        self.document = document
        self.snapshot = document.project_snapshot
        self.environ = environ
        self.staging = staging
        self.clock = clock
        self.cancellation_requested = cancellation_requested or (lambda: False)
        self.progress = progress
        self.progress_clock = progress_clock or clock
        self.runtime: TargetRuntime = runtime_factory.create(
            self.snapshot,
            TargetRuntimeContext(
                environ=environ,
                staging=staging,
                clock=clock,
                cancellation_requested=self.cancellation_requested,
                control_origin=environ.get("JIEJIAN_CONTROL_ORIGIN"),
            ),
        )
        self.actions = {item.action_id: item for item in self.snapshot.contract.actions}
        self.effects = {item.effect_id: item for item in self.snapshot.contract.effects}
        self.effect_bindings = {item.effect_id: item for item in self.snapshot.effect_bindings}
        self.bindings = {item.requirement_id: item for item in self.snapshot.observer_bindings}
        self.specs = {item.observer_id: item for item in self.snapshot.observers}
        self.observers = ObserverCoordinator(registry=default_observer_registry(), specs=self.specs, bindings=self.bindings, environ=environ, attempt_dir=staging.parent, clock=clock, cancellation_requested=self.cancellation_requested)
        self.twin_baselines: dict[str, tuple[str, ...]] = {}

    def close(self) -> None:
        """关闭 attempt Runtime；由 composition 归一化关闭失败。"""

        self.runtime.close()

    def run_case(self, case, *, twin=None, twin_role: TwinExecutionRole | None = None, allow_control_valid: bool = False) -> CaseResult:
        action = self.actions[case.action_id]
        requirements_to_run = _requirements_to_run(case, action, self.effect_bindings)
        session = self.runtime.open_case(case, action)

        def baseline_invalid(active_session, baseline, envelopes, outcomes):
            return self._baseline_inconclusive(
                active_session,
                case,
                action,
                baseline,
                envelopes,
                outcomes,
                twin=twin,
                twin_role=twin_role,
                requirements_to_run=requirements_to_run,
            )

        def validate_baseline(baseline: TargetBaselineResult) -> TargetBaselineResult:
            return _validate_twin_baseline(
                self.twin_baselines,
                twin,
                twin_role,
                baseline,
            )

        def verify(active_session, envelopes: tuple[ObservationEnvelope, ...], outcomes: tuple[ObserverOutcome, ...], execution: ExecutionFact):
            outcomes = self.observers.complete_required_outcomes(
                case,
                outcomes,
                requirements_to_run=requirements_to_run,
            )
            facts = self.observers.project_facts(
                case,
                envelopes,
                requirements_to_run=requirements_to_run,
                required_requirements=case.required_observations,
            )
            effects = self._security_effects(active_session, case, action, facts, envelopes)
            verdict, reasons = evaluate_permission_case(CaseDecisionInput(case=case, action=action, execution=execution, effects=effects, twin_role=twin_role, allow_control_valid=True if twin_role is TwinExecutionRole.ALLOW_CONTROL else allow_control_valid, baseline_integrity=True))
            verdict, reasons = _apply_required_observer_guard(
                case,
                self.bindings,
                outcomes,
                effects,
                verdict,
                reasons,
            )
            is_allow_control = twin_role is TwinExecutionRole.ALLOW_CONTROL or (
                twin_role is None
                and all(item is PermissionExpectation.ALLOW for item in case.expectations)
            )
            return CaseResult(case=case, execution_fact=execution, verdict=verdict, finding_pre_identity=case.finding_pre_identity, baseline_integrity=True, twin_snapshot=twin, twin_role=twin_role, allow_control_valid=(verdict is CaseVerdict.SAFE) if is_allow_control else allow_control_valid, requirement_bindings=tuple(self.bindings[item] for item in requirements_to_run), observation_facts=facts, security_effect_facts=effects, observations=envelopes, outcomes=outcomes, reason_codes=tuple(reasons), stage_trace=("PREPARE", "BASELINE", "BEFORE", "TARGET", "AFTER", "EVENTUAL", "RESOLVE", "VERIFICATION", "CLEANUP"))

        return CaseOrchestrator(observers=self.observers, bindings=self.bindings, clock=self.clock, cancellation_requested=self.cancellation_requested, progress=self.progress, progress_clock=self.progress_clock).run(session, case, action=action, verify=verify, finding_pre_identity=case.finding_pre_identity, twin=twin, twin_role=twin_role, allow_control_valid=allow_control_valid, baseline_validate=validate_baseline, baseline_invalid=baseline_invalid, requirements_to_run=requirements_to_run)

    def _baseline_inconclusive(self, session, case, action, baseline, envelopes, outcomes, *, twin, twin_role, requirements_to_run) -> CaseResult:
        """基线不可比时在 TARGET 前形成 INCONCLUSIVE，并仍由编排器执行 cleanup。"""

        reason = baseline.reason_codes[0] if baseline.reason_codes else "BASELINE_INTEGRITY_INVALID"
        observation_facts = self.observers.project_facts(
            case,
            envelopes,
            requirements_to_run=requirements_to_run,
            required_requirements=case.required_observations,
        )
        effects = self._security_effects(session, case, action, observation_facts, envelopes, baseline_integrity=False)
        execution = ExecutionFact(
            case_id=case.case_id,
            action_id=case.action_id,
            target_type=self.snapshot.target_type,
            outcome=ExecutionOutcome.UNKNOWN,
            execution_marker=case.case_id,
            input_hash=hashlib.sha256(b"").hexdigest(),
            output_hash=hashlib.sha256(b"").hexdigest(),
            reason_codes=(reason,),
        )
        failed_outcomes = dict(outcomes)
        required = set(case.required_observations)
        for requirement in requirements_to_run:
            binding = self.bindings[requirement]
            spec = self.specs[binding.observer_id]
            if requirement in required or binding.observer_id not in failed_outcomes:
                failed_outcomes[binding.observer_id] = ObserverOutcome(
                    observer_id=spec.observer_id,
                    required=requirement in required,
                    status=ObserverOutcomeStatus.INCONCLUSIVE,
                    reason_codes=(reason,),
                )
        return CaseResult(
            case=case,
            execution_fact=execution,
            verdict=CaseVerdict.INCONCLUSIVE,
            finding_pre_identity=case.finding_pre_identity,
            baseline_integrity=False,
            twin_snapshot=twin,
            twin_role=twin_role,
            allow_control_valid=False,
            requirement_bindings=tuple(self.bindings[item] for item in requirements_to_run),
            observation_facts=observation_facts,
            security_effect_facts=effects,
            observations=envelopes,
            outcomes=tuple(failed_outcomes.values()),
            reason_codes=(reason,),
            stage_trace=("PREPARE", "BASELINE", "VERIFICATION", "CLEANUP"),
        )

    def _security_effects(self, session, case, action, observations, envelopes, *, baseline_integrity: bool = True):
        facts = []
        for effect_id in action.effect_ids:
            effect = self.effects[effect_id]
            binding = self.effect_bindings[effect_id]
            for resource_id in case.resource_ids:
                proof = session.build_disclosure_proof(effect, resource_id, envelopes)
                facts.append(aggregate_security_effect(effect, resource_id=resource_id, required_requirement_ids=binding.required_channels, corroborating_requirement_ids=binding.corroborating_channels, observations=observations, baseline_integrity=baseline_integrity, disclosure_proof=proof))
        return tuple(facts)


def execute_runner_attempt(input_path: Path, staging_dir: Path, *, environ: Mapping[str, str] | None = None, finished_at_us: Callable[[], int] | None = None) -> int:
    """Worker 窄入口；Target Runtime 的唯一生产注册由 composition 提供。"""

    from product.backend.infra.runtime.runner.composition import execute_attempt

    return execute_attempt(input_path, staging_dir, environ=environ, finished_at_us=finished_at_us)
