# 验证隔离 Runner 运行时中的目标运行时替身编排。

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import (
    ExecutionFact,
    ExecutionOutcome,
    ObservationFact,
    ObservedEffect,
    TargetType,
    TemporalClosure,
    aggregate_security_effect,
)
from product.backend.core.verification.permissions.coverage import (
    PermissionMutationCase,
    RetentionReason,
)
from product.backend.core.verification.permissions.evaluation import (
    CaseDecisionInput,
    evaluate_permission_case,
)
from product.backend.core.verification.permissions import (
    ActionDefinition,
    CoverageDimension,
    PermissionContext,
    PermissionExpectation,
    SecurityEffectDefinition,
    SecurityEffectKind,
)
from product.backend.infra.execution.port import TargetBaselineResult, TargetRuntimeContext
from product.backend.infra.execution.registry import TargetRuntimeRegistry
from product.backend.infra.runtime.runner.case_orchestrator import CaseOrchestrator, CaseResult
from product.protocols import ObservationPhase


@dataclass(frozen=True, slots=True)
class _FakeSnapshot:
    project_id: str = "fake-project"
    target_type: TargetType = TargetType.WEB
    contract: object = None
    plan: object = None
    differential_plan: object = None
    observers: tuple[object, ...] = ()
    effect_bindings: tuple[object, ...] = ()
    observer_bindings: tuple[object, ...] = ()


class _FakeSession:
    def __init__(self) -> None:
        self.events: list[str] = []

    def prepare(self) -> None:
        self.events.append("prepare")

    def observe_target(self, *args):
        self.events.append("observe_target")
        return None

    def evaluate_baseline(self, envelopes, *, ignored_case_fields=()):
        del ignored_case_fields
        self.events.append("baseline")
        return TargetBaselineResult(valid=True, comparison_fingerprints=("a" * 64,))

    def execute_target(self):
        self.events.append("target")
        return ExecutionFact(case_id="case-" + "a" * 32, action_id="view", target_type=TargetType.WEB, outcome=ExecutionOutcome.ACCEPTED, execution_marker="case-fake", input_hash="a" * 64, output_hash="b" * 64)

    def resolve_execution(self, observations):
        self.events.append("resolve")
        return ExecutionFact(case_id="case-" + "a" * 32, action_id="view", target_type=TargetType.WEB, outcome=ExecutionOutcome.ACCEPTED, execution_marker="case-fake", input_hash="a" * 64, output_hash="b" * 64)

    def build_disclosure_proof(self, *args):
        return None

    def cleanup(self) -> None:
        self.events.append("cleanup")


class _FakeRuntime:
    def __init__(self) -> None:
        self.session = _FakeSession()

    def open_case(self, case, action):
        return self.session

    def close(self) -> None:
        return None


class _NoopObserverCoordinator:
    def observe_phase(self, *_args) -> bool:
        return False


class _UnavailableBaselineCoordinator:
    def observe_phase(self, _session, _case, phase, *_args) -> bool:
        return phase is ObservationPhase.BASELINE


class _InvalidBaselineSession(_FakeSession):
    def evaluate_baseline(self, envelopes, *, ignored_case_fields=()):
        del ignored_case_fields
        self.events.append("baseline")
        return TargetBaselineResult(
            valid=False,
            comparison_fingerprints=("b" * 64,),
            reason_codes=("TWIN_BASELINE_MISMATCH",),
        )


class _FakeFactory:
    kind = "TEST_FAKE"

    def __init__(self) -> None:
        self.runtime = _FakeRuntime()

    def create(self, snapshot, context):
        del snapshot, context
        return self.runtime


def _case() -> PermissionMutationCase:
    return PermissionMutationCase(
        case_id="case-" + "a" * 32,
        fingerprint="b" * 64,
        finding_pre_identity="c" * 64,
        source_rule_ids=("rule",),
        dimensions=(CoverageDimension.RELATION,),
        retention_reason=RetentionReason.EXPLICIT_ALLOW_BASELINE,
        subject_id="member",
        action_id="view",
        resource_ids=("document",),
        expectations=(PermissionExpectation.ALLOW,),
        relation_paths=(("owns",),),
        context=PermissionContext(resource_ids=("document",)),
        required_observations=("resource_state",),
    )


def test_test_fake_runtime_uses_common_case_orchestration_without_web() -> None:
    factory = _FakeFactory()
    registry = TargetRuntimeRegistry()
    registry.register(factory)
    runtime = registry.create(
        "TEST_FAKE",
        _FakeSnapshot(),
        TargetRuntimeContext(environ={}, staging=Path("."), clock=lambda: 1, cancellation_requested=lambda: False),
    )
    case = _case()
    action = ActionDefinition(action_id="view", effect_ids=("document-mutated",))
    coordinator = _NoopObserverCoordinator()

    def verify(_session, observations, outcomes, execution):
        observation_fact = ObservationFact(
            requirement_id="resource_state",
            resource_id="document",
            effect=ObservedEffect.CONFIRMED,
            complete=True,
            reliable=True,
            correlated=True,
            temporal_closure=TemporalClosure.CLOSED,
        )
        effect_fact = aggregate_security_effect(
            SecurityEffectDefinition(
                effect_id="document-mutated",
                kind=SecurityEffectKind.STATE_MUTATION,
                resource_type="document",
            ),
            resource_id="document",
            required_requirement_ids=("resource_state",),
            corroborating_requirement_ids=(),
            observations=(observation_fact,),
            baseline_integrity=True,
        )
        verdict, reasons = evaluate_permission_case(
            CaseDecisionInput(
                case=case,
                action=action,
                execution=execution,
                effects=(effect_fact,),
                allow_control_valid=False,
                baseline_integrity=True,
            )
        )
        return CaseResult(
            case=case,
            execution_fact=execution,
            verdict=verdict,
            finding_pre_identity=case.finding_pre_identity,
            baseline_integrity=True,
            observation_facts=(observation_fact,),
            security_effect_facts=(effect_fact,),
            observations=observations,
            outcomes=outcomes,
            reason_codes=reasons,
        )

    result = CaseOrchestrator(observers=coordinator, bindings={}, clock=lambda: 1, cancellation_requested=lambda: False).run(
        runtime.open_case(case, action),
        case,
        action=action,
        finding_pre_identity=case.finding_pre_identity,
        verify=verify,
    )

    assert result.verdict is CaseVerdict.SAFE
    assert result.execution_fact.outcome is ExecutionOutcome.ACCEPTED
    assert result.security_effect_facts[0].state is ObservedEffect.CONFIRMED
    assert factory.runtime.session.events == ["prepare", "baseline", "target", "resolve", "cleanup"]


def test_invalid_baseline_stops_before_target_and_still_cleans_up() -> None:
    session = _InvalidBaselineSession()
    case = _case()
    action = ActionDefinition(action_id="view", effect_ids=("document-mutated",))
    coordinator = _NoopObserverCoordinator()

    result = CaseOrchestrator(observers=coordinator, bindings={}, clock=lambda: 1, cancellation_requested=lambda: False).run(
        session,
        case,
        action=action,
        finding_pre_identity=case.finding_pre_identity,
        verify=lambda *_args: (_ for _ in ()).throw(AssertionError("TARGET 后验证不应执行")),
        baseline_invalid=lambda _session, baseline, _observations, _outcomes: baseline.reason_codes,
    )

    assert result == ("TWIN_BASELINE_MISMATCH",)
    assert session.events == ["prepare", "baseline", "cleanup"]


def test_unavailable_baseline_stops_before_target_and_still_cleans_up() -> None:
    session = _FakeSession()
    case = _case()
    action = ActionDefinition(action_id="view", effect_ids=("document-mutated",))

    result = CaseOrchestrator(
        observers=_UnavailableBaselineCoordinator(),
        bindings={},
        clock=lambda: 1,
        cancellation_requested=lambda: False,
    ).run(
        session,
        case,
        action=action,
        finding_pre_identity=case.finding_pre_identity,
        verify=lambda *_args: (_ for _ in ()).throw(
            AssertionError("BASELINE 不可用时不应执行 TARGET 后验证")
        ),
        baseline_invalid=lambda _session, baseline, _observations, _outcomes: baseline,
    )

    assert result.valid is False
    assert result.reason_codes == ("BASELINE_OBSERVATION_INCOMPLETE",)
    assert session.events == ["prepare", "cleanup"]
