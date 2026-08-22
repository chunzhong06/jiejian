from __future__ import annotations

import pytest

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.differential import TwinExecutionRole
from product.backend.core.verification.facts import (
    ExecutionFact,
    ExecutionOutcome,
    ObservedEffect,
    SecurityEffectFact,
    TargetType,
    TemporalClosure,
)
from product.backend.core.verification.permission_coverage import (
    PermissionMutationCase,
    RetentionReason,
)
from product.backend.core.verification.permission_evaluation import (
    CaseDecisionInput,
    evaluate_permission_case,
)
from product.backend.core.verification.permissions import (
    ActionDefinition,
    BatchAuthorizationMode,
    CoverageDimension,
    PermissionContext,
    PermissionExpectation,
    SecurityEffectKind,
)


pytestmark = pytest.mark.essential


def _case(expectation: PermissionExpectation) -> PermissionMutationCase:
    return PermissionMutationCase(
        case_id="case-" + "a" * 32,
        fingerprint="b" * 64,
        finding_pre_identity="c" * 64,
        source_rule_ids=("rule",),
        dimensions=(CoverageDimension.RELATION,),
        retention_reason=RetentionReason.EXPLICIT_DENY_RISK,
        subject_id="member",
        action_id="view",
        resource_ids=("document",),
        expectations=(expectation,),
        relation_paths=(("owns",),),
        context=PermissionContext(resource_ids=("document",)),
        required_observations=("resource_state",),
    )


def _effect(state: ObservedEffect, *, baseline_integrity: bool = True) -> SecurityEffectFact:
    complete = state is not ObservedEffect.UNKNOWN
    return SecurityEffectFact(
        effect_id="document-mutated",
        kind=SecurityEffectKind.STATE_MUTATION,
        resource_id="document",
        state=state,
        complete=complete,
        reliable=complete,
        correlated=complete,
        temporal_closure=TemporalClosure.CLOSED if complete else TemporalClosure.UNKNOWN,
        baseline_integrity=baseline_integrity,
        source_requirement_ids=("resource_state",),
        reason_codes=() if complete else ("EFFECT_STATE_UNKNOWN",),
    )


def _input(
    expectation: PermissionExpectation,
    outcome: ExecutionOutcome,
    effect: ObservedEffect,
    *,
    allow_control_valid: bool = True,
    baseline_integrity: bool = True,
) -> CaseDecisionInput:
    case = _case(expectation)
    execution = ExecutionFact(
        case_id=case.case_id,
        action_id=case.action_id,
        target_type=TargetType.WEB,
        outcome=outcome,
        execution_marker=case.case_id,
        input_hash="a" * 64,
        output_hash="b" * 64,
        reason_codes=() if outcome in {ExecutionOutcome.ACCEPTED, ExecutionOutcome.DENIED} else ("TRANSPORT_FAILURE",),
    )
    return CaseDecisionInput(
        case=case,
        action=ActionDefinition(action_id="view", effect_ids=("document-mutated",)),
        execution=execution,
        effects=(_effect(effect, baseline_integrity=baseline_integrity),),
        twin_role=TwinExecutionRole.ALLOW_CONTROL if expectation is PermissionExpectation.ALLOW else TwinExecutionRole.DENY_VARIANT,
        allow_control_valid=allow_control_valid,
        baseline_integrity=baseline_integrity,
    )


def test_deny_twin_needs_valid_allow_control_and_closed_absence_to_pass() -> None:
    assert evaluate_permission_case(
        _input(PermissionExpectation.DENY, ExecutionOutcome.DENIED, ObservedEffect.ABSENT)
    ) == (CaseVerdict.SAFE, ())
    assert evaluate_permission_case(
        _input(
            PermissionExpectation.DENY,
            ExecutionOutcome.DENIED,
            ObservedEffect.ABSENT,
            allow_control_valid=False,
        )
    )[0] is CaseVerdict.INCONCLUSIVE


def test_deny_acceptance_or_confirmed_effect_blocks_asymmetrically() -> None:
    assert evaluate_permission_case(
        _input(PermissionExpectation.DENY, ExecutionOutcome.ACCEPTED, ObservedEffect.ABSENT)
    )[0] is CaseVerdict.VULNERABLE
    assert evaluate_permission_case(
        _input(
            PermissionExpectation.DENY,
            ExecutionOutcome.DENIED,
            ObservedEffect.CONFIRMED,
            allow_control_valid=False,
            baseline_integrity=False,
        )
    )[0] is CaseVerdict.VULNERABLE


def test_unknown_effect_or_invalid_baseline_is_inconclusive() -> None:
    assert evaluate_permission_case(
        _input(PermissionExpectation.DENY, ExecutionOutcome.DENIED, ObservedEffect.UNKNOWN)
    )[0] is CaseVerdict.INCONCLUSIVE
    assert evaluate_permission_case(
        _input(
            PermissionExpectation.DENY,
            ExecutionOutcome.DENIED,
            ObservedEffect.UNKNOWN,
            baseline_integrity=False,
        )
    )[0] is CaseVerdict.INCONCLUSIVE


def test_allow_control_requires_accepted_execution_and_confirmed_effect() -> None:
    accepted = _input(
        PermissionExpectation.ALLOW,
        ExecutionOutcome.ACCEPTED,
        ObservedEffect.CONFIRMED,
    )
    assert evaluate_permission_case(accepted) == (CaseVerdict.SAFE, ())
    assert evaluate_permission_case(
        accepted.model_copy(update={"twin_role": None})
    ) == (CaseVerdict.SAFE, ())
    assert evaluate_permission_case(
        _input(PermissionExpectation.ALLOW, ExecutionOutcome.DENIED, ObservedEffect.CONFIRMED)
    )[0] is CaseVerdict.INCONCLUSIVE


def test_mixed_batch_without_a_twin_never_passes_but_confirmed_denied_effect_blocks() -> None:
    case = PermissionMutationCase(
        case_id="case-" + "d" * 32,
        fingerprint="e" * 64,
        finding_pre_identity="f" * 64,
        source_rule_ids=("mixed-batch",),
        dimensions=(CoverageDimension.BULK,),
        retention_reason=RetentionReason.BATCH_AUTHORIZATION,
        subject_id="member",
        action_id="batch",
        resource_ids=("foreign", "owned"),
        expectations=(PermissionExpectation.DENY, PermissionExpectation.ALLOW),
        relation_paths=((), ("owns",)),
        context=PermissionContext(resource_ids=("foreign", "owned")),
        required_observations=("resource_state",),
        batch_mode=BatchAuthorizationMode.MIXED_AUTHORIZATION,
        atomic=True,
    )
    execution = ExecutionFact(
        case_id=case.case_id,
        action_id=case.action_id,
        target_type=TargetType.WEB,
        outcome=ExecutionOutcome.DENIED,
        execution_marker=case.case_id,
        input_hash="a" * 64,
        output_hash="b" * 64,
    )
    effects = tuple(
        _effect(ObservedEffect.ABSENT).model_copy(update={"resource_id": resource_id})
        for resource_id in case.resource_ids
    )
    decision = CaseDecisionInput(
        case=case,
        action=ActionDefinition(action_id="batch", effect_ids=("document-mutated",), is_batch=True),
        execution=execution,
        effects=effects,
        allow_control_valid=False,
        baseline_integrity=True,
    )
    assert evaluate_permission_case(decision)[0] is CaseVerdict.INCONCLUSIVE
    changed = decision.model_copy(
        update={"effects": (effects[0].model_copy(update={"state": ObservedEffect.CONFIRMED}), effects[1])}
    )
    assert evaluate_permission_case(changed)[0] is CaseVerdict.VULNERABLE
