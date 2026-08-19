from __future__ import annotations

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, ObservationFact, ObservedEffect, TargetType
from product.backend.core.verification.permission_coverage import PermissionMutationCase, RetentionReason
from product.backend.core.verification.permission_evaluation import CaseDecisionInput, evaluate_permission_case
from product.backend.core.verification.permissions import ActionDefinition, BatchAuthorizationMode, CoverageDimension, PermissionContext, PermissionExpectation


def _case(expectation: PermissionExpectation, *, requirement: str = "resource_state") -> PermissionMutationCase:
    return PermissionMutationCase(case_id="case-" + "a" * 32, fingerprint="b" * 64, finding_pre_identity="c" * 64, source_rule_ids=("rule",), dimensions=(CoverageDimension.RELATION,), retention_reason=RetentionReason.EXPLICIT_DENY_RISK, subject_id="member", action_id="view", resource_ids=("document",), expectations=(expectation,), relation_paths=(("owns",),), context=PermissionContext(resource_ids=("document",)), required_observations=(requirement,))


def _input(expectation: PermissionExpectation, outcome: ExecutionOutcome, effect: ObservedEffect | None = ObservedEffect.ABSENT, *, complete: bool = True) -> CaseDecisionInput:
    case = _case(expectation)
    observations = () if effect is None else (ObservationFact(requirement_id="resource_state", resource_id="document", effect=effect, complete=complete, reliable=complete, reason_codes=() if complete else ("OBSERVATION_INCOMPLETE",)),)
    execution = ExecutionFact(case_id=case.case_id, action_id=case.action_id, target_type=TargetType.WEB, outcome=outcome, execution_marker=case.case_id, input_hash="a" * 64, output_hash="b" * 64, reason_codes=() if outcome in {ExecutionOutcome.ACCEPTED, ExecutionOutcome.DENIED} else ("TRANSPORT_FAILURE",))
    return CaseDecisionInput(case=case, action=ActionDefinition(action_id="view"), execution=execution, observations=observations)


def test_denied_execution_with_complete_no_effect_is_safe() -> None:
    assert evaluate_permission_case(_input(PermissionExpectation.DENY, ExecutionOutcome.DENIED)) == (CaseVerdict.SAFE, ())


def test_denied_permission_with_accepted_execution_is_vulnerable() -> None:
    assert evaluate_permission_case(_input(PermissionExpectation.DENY, ExecutionOutcome.ACCEPTED))[0] is CaseVerdict.VULNERABLE


def test_denied_execution_with_confirmed_effect_is_vulnerable() -> None:
    assert evaluate_permission_case(_input(PermissionExpectation.DENY, ExecutionOutcome.DENIED, ObservedEffect.CONFIRMED))[0] is CaseVerdict.VULNERABLE


def test_missing_or_unknown_observation_is_inconclusive() -> None:
    assert evaluate_permission_case(_input(PermissionExpectation.DENY, ExecutionOutcome.DENIED, None))[0] is CaseVerdict.INCONCLUSIVE
    assert evaluate_permission_case(_input(PermissionExpectation.DENY, ExecutionOutcome.DENIED, ObservedEffect.UNKNOWN, complete=False))[0] is CaseVerdict.INCONCLUSIVE


def test_allow_baseline_rejection_is_inconclusive() -> None:
    assert evaluate_permission_case(_input(PermissionExpectation.ALLOW, ExecutionOutcome.DENIED))[0] is CaseVerdict.INCONCLUSIVE


def test_atomic_mixed_batch_requires_denial_without_any_side_effect() -> None:
    case = PermissionMutationCase(
        case_id="case-" + "d" * 32,
        fingerprint="e" * 64,
        finding_pre_identity="f" * 64,
        source_rule_ids=("mixed-batch",),
        dimensions=(CoverageDimension.BULK,),
        retention_reason=RetentionReason.BATCH_AUTHORIZATION,
        subject_id="member",
        action_id="batch",
        resource_ids=("owned", "foreign"),
        expectations=(PermissionExpectation.ALLOW, PermissionExpectation.DENY),
        relation_paths=(("owns",), ()),
        context=PermissionContext(resource_ids=("owned", "foreign")),
        required_observations=("resource_state",),
        batch_mode=BatchAuthorizationMode.MIXED_AUTHORIZATION,
        atomic=True,
    )
    observations = tuple(
        ObservationFact(
            requirement_id="resource_state",
            resource_id=resource_id,
            effect=effect,
            complete=True,
            reliable=True,
        )
        for resource_id, effect in (
            ("owned", ObservedEffect.ABSENT),
            ("foreign", ObservedEffect.ABSENT),
        )
    )
    denied = ExecutionFact(
        case_id=case.case_id,
        action_id=case.action_id,
        target_type=TargetType.WEB,
        outcome=ExecutionOutcome.DENIED,
        execution_marker=case.case_id,
        input_hash="a" * 64,
        output_hash="b" * 64,
    )
    decision = CaseDecisionInput(
        case=case,
        action=ActionDefinition(action_id="batch", is_batch=True, side_effect=True),
        execution=denied,
        observations=observations,
    )
    assert evaluate_permission_case(decision) == (CaseVerdict.SAFE, ())

    changed = decision.model_copy(
        update={
            "observations": (
                observations[0].model_copy(update={"effect": ObservedEffect.CONFIRMED}),
                observations[1],
            )
        }
    )
    assert evaluate_permission_case(changed)[0] is CaseVerdict.VULNERABLE
