# 将真实观察交给正式判定规则；private oracle 不进入产品输入。
from __future__ import annotations

import hashlib
from typing import Mapping
from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.breakpoints import BreakpointLocator, BreakpointResult
from product.backend.core.verification.continuity import (
    AuthorizationContinuityState,
    assess_authorization_continuity,
)
from product.backend.core.verification.differential import TwinExecutionRole
from product.backend.core.verification.facts import (
    DisclosureProof,
    ExecutionFact,
    ExecutionOutcome,
    ObservedEffect,
    SecurityEffectFact,
    TargetType,
    TemporalClosure,
)
from product.backend.core.verification.permissions import (
    ActionDefinition,
    CoverageDimension,
    PermissionContext,
    PermissionExpectation,
    SecurityEffectKind,
)
from product.backend.core.verification.permissions.coverage import (
    PermissionMutationCase,
    RetentionReason,
)
from product.backend.core.verification.permissions.evaluation import (
    CaseDecisionInput,
    evaluate_permission_case,
)
from scripts.dev.sample_test.adapter import build_validation_domain_bundle
from scripts.dev.sample_test.registry import PublicValidationCase, ValidationCaseResult
import scripts.dev.sample_test.validation.models as sample_validation_models


def _evaluate_case(
    case: PublicValidationCase,
    observation: sample_validation_models._ExecutionObservation,
) -> ValidationCaseResult:
    """把真实 fixture 事实交给既有 Permission Verification 纯判定。"""

    allow_input = _decision_input(
        case,
        expectation=PermissionExpectation.ALLOW,
        outcome=_execution_outcome(observation.allow_status),
        effect=observation.allow_effect,
        twin_role=TwinExecutionRole.ALLOW_CONTROL,
        allow_control_valid=True,
    )
    allow_verdict, _ = evaluate_permission_case(allow_input)
    allow_valid = allow_verdict is CaseVerdict.SAFE
    deny_input = _decision_input(
        case,
        expectation=PermissionExpectation.DENY,
        outcome=_execution_outcome(observation.deny_status),
        effect=observation.deny_effect,
        twin_role=TwinExecutionRole.DENY_VARIANT,
        allow_control_valid=allow_valid,
    )
    verdict, _ = evaluate_permission_case(deny_input)
    public_verdict = sample_validation_models._VERDICT[verdict]
    bundle = build_validation_domain_bundle(
        case,
        allow_trace_records=observation.allow_trace,
        deny_trace_records=observation.deny_trace,
        allow_trace_complete=observation.allow_trace_complete,
        deny_trace_complete=observation.deny_trace_complete,
        allow_effect_fact=_effect_fact(case, observation.allow_effect),
        deny_effect_fact=_effect_fact(case, observation.deny_effect),
    )
    continuity = assess_authorization_continuity(
        bundle.contract,
        bundle.twin,
        bundle.deny_effect_facts,
    )
    breakpoint = BreakpointLocator().locate(
        contract=bundle.contract,
        differential_plan=bundle.plan,
        allow_trace=bundle.allow_trace,
        deny_trace=bundle.deny_trace,
        allow_effect_facts=bundle.allow_effect_facts,
        deny_effect_facts=bundle.deny_effect_facts,
        evidence_refs=bundle.evidence_refs,
    )
    breakpoint_type, breakpoint_location, breakpoint_range, precision = (
        _breakpoint_projection(breakpoint, bundle.deny_trace)
    )
    continuity_label = {
        AuthorizationContinuityState.INTACT: "INTACT",
        AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED: "BROKEN",
        AuthorizationContinuityState.UNKNOWN: "UNKNOWN",
    }[continuity.state]
    orphan_effect = {
        AuthorizationContinuityState.INTACT: False,
        AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED: True,
        AuthorizationContinuityState.UNKNOWN: None,
    }[continuity.state]
    return ValidationCaseResult(
        case_id=case.case_id,
        application_id=case.application_id,
        mode=case.mode,
        verdict=public_verdict,
        allow_control_valid=allow_valid,
        breakpoint_type=breakpoint_type,
        breakpoint_location=breakpoint_location,
        breakpoint_range=breakpoint_range,
        precision=precision,
        effect_state=observation.deny_effect.value,
        authorization_continuity=continuity_label,
        orphan_effect_detected=orphan_effect,
        actual_identity_attributed=observation.actual_identity_attributed,
        recovery_success=observation.recovery_success,
        baseline_verdicts=_baseline_verdicts(observation),
    )


def _breakpoint_projection(
    breakpoint: BreakpointResult | None,
    deny_trace,
) -> tuple[str | None, str | None, tuple[str, ...], str | None]:
    """把生产 Locator 的事件引用投影成既有公开 validation 摘要。"""

    if breakpoint is None:
        return None, None, (), None
    events = {item.event_id: item for item in deny_trace.events}
    location = (
        events[breakpoint.first_violation_event_id].semantic_key
        if breakpoint.first_violation_event_id is not None
        else None
    )
    range_keys = tuple(
        events[event_id].semantic_key
        for event_id in (
            breakpoint.range_start_event_id,
            breakpoint.range_end_event_id,
        )
        if event_id is not None
    )
    return (
        breakpoint.breakpoint_type.value if breakpoint.breakpoint_type is not None else None,
        location,
        range_keys,
        breakpoint.precision.value,
    )


def _baseline_verdicts(
    observation: sample_validation_models._ExecutionObservation,
) -> Mapping[str, str]:
    """按公开执行事实运行三种受限基线，不复用完整判定结果。"""

    http_only = "BLOCK" if 200 <= observation.deny_status < 300 else "PASS"
    single_state = {
        ObservedEffect.CONFIRMED: "BLOCK",
        ObservedEffect.ABSENT: "PASS",
        ObservedEffect.UNKNOWN: "INCONCLUSIVE",
    }[observation.deny_effect]
    allow_accepted = 200 <= observation.allow_status < 300
    if 200 <= observation.deny_status < 300:
        authorization_regression = "BLOCK"
    elif observation.deny_status in {401, 403} and allow_accepted:
        authorization_regression = "PASS"
    else:
        authorization_regression = "INCONCLUSIVE"
    return {
        "http_only": http_only,
        "single_state": single_state,
        "authorization_regression": authorization_regression,
    }


def _decision_input(
    case: PublicValidationCase,
    *,
    expectation: PermissionExpectation,
    outcome: ExecutionOutcome,
    effect: ObservedEffect,
    twin_role: TwinExecutionRole,
    allow_control_valid: bool,
) -> CaseDecisionInput:
    digest = hashlib.sha256(case.case_id.encode("utf-8")).hexdigest()
    case_id = "case-" + digest[:32]
    mutation = PermissionMutationCase(
        case_id=case_id,
        fingerprint=digest,
        finding_pre_identity=hashlib.sha256((case.case_id + "|finding").encode()).hexdigest(),
        source_rule_ids=("validation-public-intent",),
        dimensions=(CoverageDimension.RELATION,),
        retention_reason=RetentionReason.EXPLICIT_DENY_RISK,
        subject_id=case.allow_control_identity if expectation is PermissionExpectation.ALLOW else case.identity,
        action_id=case.business_action,
        resource_ids=(case.resource,),
        expectations=(expectation,),
        relation_paths=((str(case.permission_intent.get("relation") or "relation").casefold(),),),
        context=PermissionContext(
            tenant_ids=("tenant-alpha",),
            resource_ids=(case.resource,),
        ),
        required_observations=(str(case.observation_config.get("required_channel")),),
    )
    execution = ExecutionFact(
        case_id=case_id,
        action_id=case.business_action,
        target_type=TargetType.WEB,
        outcome=outcome,
        execution_marker="validation-" + digest[:20],
        input_hash=digest,
        output_hash=hashlib.sha256((case.case_id + "|" + outcome.value).encode()).hexdigest(),
        reason_codes=("VALIDATION_EXECUTION_FAILED",) if outcome is ExecutionOutcome.FAILED else (),
    )
    effect_fact = _effect_fact(case, effect)
    return CaseDecisionInput(
        case=mutation,
        action=ActionDefinition(
            action_id=case.business_action,
            effect_ids=case.protected_effects,
        ),
        execution=execution,
        effects=(effect_fact,),
        twin_role=twin_role,
        allow_control_valid=allow_control_valid,
        baseline_integrity=True,
    )


def _effect_fact(
    case: PublicValidationCase,
    state: ObservedEffect,
) -> SecurityEffectFact:
    complete = state is not ObservedEffect.UNKNOWN
    effect_kind = SecurityEffectKind(str(case.observation_config.get("effect_kind")))
    disclosure = None
    if effect_kind is SecurityEffectKind.DATA_DISCLOSURE:
        owner_digest = hashlib.sha256((case.case_id + "|owner").encode()).hexdigest()
        response_digest = (
            owner_digest
            if state is ObservedEffect.CONFIRMED
            else hashlib.sha256((case.case_id + "|response").encode()).hexdigest()
        )
        disclosure = DisclosureProof(
            projection_version="validation-v1",
            projection_complete=complete,
            owner_digest=owner_digest,
            response_digest=response_digest,
            matched=state is ObservedEffect.CONFIRMED,
            correlation_digest=hashlib.sha256((case.case_id + "|correlation").encode()).hexdigest(),
        )
    return SecurityEffectFact(
        effect_id=case.protected_effects[0],
        kind=effect_kind,
        resource_id=case.resource,
        state=state,
        complete=complete,
        reliable=complete,
        correlated=complete,
        temporal_closure=TemporalClosure.CLOSED if complete else TemporalClosure.UNKNOWN,
        baseline_integrity=True,
        source_requirement_ids=(str(case.observation_config.get("required_channel")),),
        disclosure_proof=disclosure,
        reason_codes=() if complete else ("VALIDATION_OBSERVATION_UNAVAILABLE",),
    )


def _execution_outcome(status: int) -> ExecutionOutcome:
    if 200 <= status < 300:
        return ExecutionOutcome.ACCEPTED
    if status in {401, 403}:
        return ExecutionOutcome.DENIED
    return ExecutionOutcome.FAILED
