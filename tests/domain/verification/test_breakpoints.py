# 验证被动 Locator 只凭冻结权限事实定位六类断裂，并按证据边界降级精度。
from __future__ import annotations

from dataclasses import dataclass

from pathlib import Path

import pytest

from pydantic import ValidationError

from product.backend.domain.verification.breakpoints.locator import BreakpointLocator
from product.backend.domain.verification.breakpoints.models import BreakpointPrecision, BreakpointResult, BreakpointType

from product.backend.domain.verification.facts import ObservedEffect, SecurityEffectFact, TemporalClosure

from product.backend.domain.verification.permissions.contract import PermissionContract

from product.backend.domain.verification.permissions.coverage import build_permission_coverage_plan

from product.backend.domain.verification.trace import ExecutionTrace, TraceAuthorityScope, TraceAuthorizationDecision, TraceCorrelationKind, TraceEvent, TraceEventKind

from product.protocols.web.profile import WebExecutionProfile

from tests.support.builders.runtime.runner import write_web_test_profile

EVIDENCE_REF = "ev_bbbbbbbbbbbbbbbbbbbb"

@dataclass(frozen=True, slots=True)
class FrozenContext:
    contract: PermissionContract
    plan: object
    allow_case_id: str
    deny_case_id: str
    allow_subject_id: str
    deny_subject_id: str
    action_id: str
    resource_id: str
    effect_id: str
    effect_kind: object

@pytest.fixture()
def frozen_context(tmp_path: Path) -> FrozenContext:
    profile_path, contract_path = write_web_test_profile(
        tmp_path, include_comparison_subject=True
    )
    contract = PermissionContract.model_validate_json(
        contract_path.read_text(encoding="utf-8")
    )
    profile = WebExecutionProfile.model_validate_json(
        profile_path.read_text(encoding="utf-8")
    )
    coverage = build_permission_coverage_plan(
        contract,
        engine_version="coverage-v2",
        seed=profile.seed,
        case_budget=profile.case_budget,
        max_relation_depth=profile.max_relation_depth,
    )
    plan = profile.build_snapshot(contract, coverage).differential_plan
    twin = plan.twins[0]
    action = next(
        item for item in contract.actions if item.action_id == twin.invariant.action_id
    )
    effect = next(item for item in contract.effects if item.effect_id in action.effect_ids)
    return FrozenContext(
        contract=contract,
        plan=plan,
        allow_case_id=twin.allow_case.case_id,
        deny_case_id=twin.deny_case.case_id,
        allow_subject_id=twin.allow_case.subject_id,
        deny_subject_id=twin.deny_case.subject_id,
        action_id=twin.invariant.action_id,
        resource_id=twin.invariant.resource_ids[0],
        effect_id=effect.effect_id,
        effect_kind=effect.kind,
    )

def _event(
    context: FrozenContext,
    *,
    case_id: str,
    event_id: str,
    kind: TraceEventKind,
    semantic_key: str,
    parent_ids: tuple[str, ...] = (),
    subject_id: str | None = None,
    actor_id: str | None = None,
    credential_source: str | None = None,
    authority_scope: TraceAuthorityScope | None = None,
    decision: TraceAuthorizationDecision | None = None,
    effect: bool = False,
    recorded_at_us: int = 1,
) -> TraceEvent:
    return TraceEvent(
        event_id=event_id,
        parent_event_ids=parent_ids,
        case_id=case_id,
        action_id=context.action_id,
        resource_ids=(context.resource_id,),
        kind=kind,
        semantic_key=semantic_key,
        subject_id=subject_id,
        actor_id=actor_id,
        credential_source=credential_source,
        authority_scope=authority_scope or TraceAuthorityScope(),
        authorization_decision=decision,
        effect_id=context.effect_id if effect else None,
        source_component="collaboration-server",
        source_location="permission-path",
        correlation_kind=TraceCorrelationKind.EXPLICIT_PARENT,
        evidence_refs=(EVIDENCE_REF,),
        recorded_at_us=recorded_at_us,
    )

def _trace(
    context: FrozenContext,
    *,
    allow: bool,
    events: tuple[TraceEvent, ...],
    complete: bool = True,
) -> ExecutionTrace:
    return ExecutionTrace(
        case_id=context.allow_case_id if allow else context.deny_case_id,
        action_id=context.action_id,
        planned_subject_id=(
            context.allow_subject_id if allow else context.deny_subject_id
        ),
        events=events,
        complete=complete,
        reason_codes=() if complete else ("TRACE_AUDIT_INCOMPLETE",),
    )

def _allow_trace(context: FrozenContext, *, prefix: str = "allow") -> ExecutionTrace:
    case_id = context.allow_case_id
    entry = _event(
        context,
        case_id=case_id,
        event_id=f"{prefix}-entry",
        kind=TraceEventKind.ENTRY,
        semantic_key="request_received",
        subject_id=context.allow_subject_id,
        actor_id=context.allow_subject_id,
        recorded_at_us=400,
    )
    identity = _event(
        context,
        case_id=case_id,
        event_id=f"{prefix}-identity",
        kind=TraceEventKind.IDENTITY,
        semantic_key="server_identity_resolved",
        parent_ids=(entry.event_id,),
        subject_id=context.allow_subject_id,
        actor_id=context.allow_subject_id,
        credential_source="session-cookie",
        recorded_at_us=300,
    )
    authorization = _event(
        context,
        case_id=case_id,
        event_id=f"{prefix}-authorization",
        kind=TraceEventKind.AUTHORIZATION,
        semantic_key="authorization_decided",
        parent_ids=(identity.event_id,),
        subject_id=context.allow_subject_id,
        actor_id=context.allow_subject_id,
        credential_source="session-cookie",
        authority_scope=TraceAuthorityScope(
            allowed_action_ids=(context.action_id,),
            allowed_resource_ids=(context.resource_id,),
        ),
        decision=TraceAuthorizationDecision.ALLOW,
        recorded_at_us=200,
    )
    effect = _event(
        context,
        case_id=case_id,
        event_id=f"{prefix}-effect",
        kind=TraceEventKind.PERSISTENT_EFFECT,
        semantic_key="export_request_created",
        parent_ids=(authorization.event_id,),
        subject_id=context.allow_subject_id,
        actor_id=context.allow_subject_id,
        effect=True,
        recorded_at_us=100,
    )
    # 输入顺序和时间都与因果顺序相反，验证定位不依赖列表位置或时间戳。
    return _trace(
        context,
        allow=True,
        events=(effect, identity, entry, authorization),
    )

def _effect_fact(
    context: FrozenContext, state: ObservedEffect
) -> SecurityEffectFact:
    return SecurityEffectFact(
        effect_id=context.effect_id,
        kind=context.effect_kind,
        resource_id=context.resource_id,
        state=state,
        complete=True,
        reliable=True,
        correlated=True,
        temporal_closure=TemporalClosure.CLOSED,
        baseline_integrity=True,
        source_requirement_ids=("resource-state",),
    )

def _locate(
    context: FrozenContext,
    deny_trace: ExecutionTrace,
    *,
    allow_trace: ExecutionTrace | None = None,
    deny_state: ObservedEffect = ObservedEffect.CONFIRMED,
) -> BreakpointResult | None:
    return BreakpointLocator().locate(
        contract=context.contract,
        differential_plan=context.plan,
        allow_trace=allow_trace or _allow_trace(context),
        deny_trace=deny_trace,
        allow_effect_facts=(_effect_fact(context, ObservedEffect.CONFIRMED),),
        deny_effect_facts=(_effect_fact(context, deny_state),),
        evidence_refs=(EVIDENCE_REF,),
    )

def _base_events(
    context: FrozenContext,
    *,
    prefix: str = "deny",
    actual_subject: str | None = None,
) -> tuple[TraceEvent, TraceEvent]:
    case_id = context.deny_case_id
    subject = actual_subject or context.deny_subject_id
    entry = _event(
        context,
        case_id=case_id,
        event_id=f"{prefix}-entry",
        kind=TraceEventKind.ENTRY,
        semantic_key="request_received",
        subject_id=subject,
        actor_id=subject,
        recorded_at_us=20,
    )
    identity = _event(
        context,
        case_id=case_id,
        event_id=f"{prefix}-identity",
        kind=TraceEventKind.IDENTITY,
        semantic_key="server_identity_resolved",
        parent_ids=(entry.event_id,),
        subject_id=subject,
        actor_id=subject,
        credential_source="session-cookie",
        recorded_at_us=10,
    )
    return entry, identity

def _authorization(
    context: FrozenContext,
    parent_id: str,
    *,
    event_id: str = "deny-authorization",
    decision: TraceAuthorizationDecision = TraceAuthorizationDecision.ALLOW,
    subject_id: str | None = None,
) -> TraceEvent:
    subject = subject_id or context.deny_subject_id
    return _event(
        context,
        case_id=context.deny_case_id,
        event_id=event_id,
        kind=TraceEventKind.AUTHORIZATION,
        semantic_key="authorization_decided",
        parent_ids=(parent_id,),
        subject_id=subject,
        actor_id=subject,
        credential_source="session-cookie",
        authority_scope=TraceAuthorityScope(
            allowed_action_ids=(context.action_id,),
            allowed_resource_ids=(context.resource_id,),
        ),
        decision=decision,
        recorded_at_us=30,
    )

def _protected(
    context: FrozenContext,
    parent_id: str | None,
    *,
    event_id: str = "deny-effect",
    subject_id: str | None = None,
    actor_id: str | None = None,
) -> TraceEvent:
    subject = subject_id or context.deny_subject_id
    return _event(
        context,
        case_id=context.deny_case_id,
        event_id=event_id,
        kind=TraceEventKind.PERSISTENT_EFFECT,
        semantic_key="export_request_created",
        parent_ids=() if parent_id is None else (parent_id,),
        subject_id=subject,
        actor_id=actor_id or subject,
        effect=True,
        recorded_at_us=40,
    )

def test_locates_authorization_missing(frozen_context: FrozenContext) -> None:
    entry, identity = _base_events(frozen_context)
    effect = _protected(frozen_context, identity.event_id)

    result = _locate(
        frozen_context,
        _trace(frozen_context, allow=False, events=(effect, entry, identity)),
    )

    assert result is not None
    assert result.breakpoint_type is BreakpointType.AUTHORIZATION_MISSING
    assert result.precision is BreakpointPrecision.EXACT
    assert result.first_violation_event_id == effect.event_id

def test_locates_authorization_late_for_representative_sample_fact(
    frozen_context: FrozenContext,
) -> None:
    entry, identity = _base_events(frozen_context)
    effect = _protected(frozen_context, identity.event_id)
    authorization = _authorization(
        frozen_context,
        effect.event_id,
        decision=TraceAuthorizationDecision.DENY,
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(authorization, effect, entry, identity),
        ),
    )

    assert result is not None
    assert result.breakpoint_type is BreakpointType.AUTHORIZATION_LATE
    assert result.precision is BreakpointPrecision.EXACT
    assert result.last_known_good_event_id == identity.event_id
    assert authorization.event_id in result.downstream_event_ids

def test_target_local_identity_does_not_become_false_identity_substitution(
    frozen_context: FrozenContext,
) -> None:
    local_subject = "bob"
    entry, identity = _base_events(
        frozen_context,
        actual_subject=local_subject,
    )
    effect = _protected(
        frozen_context,
        identity.event_id,
        subject_id=local_subject,
        actor_id=local_subject,
    )
    authorization = _authorization(
        frozen_context,
        effect.event_id,
        decision=TraceAuthorizationDecision.DENY,
        subject_id=local_subject,
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(authorization, effect, entry, identity),
        ),
    )

    assert result is not None
    assert result.breakpoint_type is BreakpointType.AUTHORIZATION_LATE
    assert result.precision is BreakpointPrecision.EXACT
    assert result.first_violation_event_id == effect.event_id

def test_locates_authorization_bypass(frozen_context: FrozenContext) -> None:
    entry, identity = _base_events(frozen_context)
    authorization = _authorization(
        frozen_context,
        identity.event_id,
        decision=TraceAuthorizationDecision.DENY,
    )
    effect = _protected(frozen_context, identity.event_id)

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(entry, identity, authorization, effect),
        ),
    )

    assert result is not None
    assert result.breakpoint_type is BreakpointType.AUTHORIZATION_BYPASS

def test_locates_identity_substitution(frozen_context: FrozenContext) -> None:
    actual = frozen_context.allow_subject_id
    entry, identity = _base_events(frozen_context, actual_subject=actual)
    authorization = _authorization(
        frozen_context,
        identity.event_id,
        subject_id=actual,
    )
    effect = _protected(
        frozen_context,
        authorization.event_id,
        subject_id=actual,
        actor_id=actual,
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(effect, authorization, identity, entry),
        ),
    )

    assert result is not None
    assert result.breakpoint_type is BreakpointType.IDENTITY_SUBSTITUTION
    assert result.first_violation_event_id == identity.event_id

def test_locates_authority_expansion(frozen_context: FrozenContext) -> None:
    entry, identity = _base_events(frozen_context)
    authorization = _authorization(frozen_context, identity.event_id)
    delegation = _event(
        frozen_context,
        case_id=frozen_context.deny_case_id,
        event_id="deny-delegation",
        kind=TraceEventKind.DELEGATION,
        semantic_key="export_job_started",
        parent_ids=(authorization.event_id,),
        subject_id=frozen_context.deny_subject_id,
        actor_id="export-worker",
        authority_scope=TraceAuthorityScope(
            allowed_action_ids=("administrative-export",),
            allowed_resource_ids=(frozen_context.resource_id,),
            origin_authorization_event_id=authorization.event_id,
        ),
        recorded_at_us=40,
    )
    effect = _protected(
        frozen_context,
        delegation.event_id,
        actor_id="export-worker",
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(effect, delegation, authorization, identity, entry),
        ),
    )

    assert result is not None
    assert result.breakpoint_type is BreakpointType.AUTHORITY_EXPANSION
    assert result.first_violation_event_id == delegation.event_id

def test_locates_compensation_masking(frozen_context: FrozenContext) -> None:
    entry, identity = _base_events(frozen_context)
    authorization = _authorization(frozen_context, identity.event_id)
    effect = _protected(frozen_context, authorization.event_id)
    recovery = _event(
        frozen_context,
        case_id=frozen_context.deny_case_id,
        event_id="deny-recovery",
        kind=TraceEventKind.RECOVERY,
        semantic_key="export_state_recovered",
        parent_ids=(effect.event_id,),
        subject_id=frozen_context.deny_subject_id,
        actor_id=frozen_context.deny_subject_id,
        recorded_at_us=50,
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(recovery, effect, authorization, identity, entry),
        ),
    )

    assert result is not None
    assert result.breakpoint_type is BreakpointType.COMPENSATION_MASKING
    assert result.first_violation_event_id == recovery.event_id
    assert effect.event_id not in result.downstream_event_ids

def test_keeps_one_primary_and_records_later_compensation_as_amplifier(
    frozen_context: FrozenContext,
) -> None:
    entry, identity = _base_events(frozen_context)
    effect = _protected(frozen_context, identity.event_id)
    authorization = _authorization(
        frozen_context,
        effect.event_id,
        decision=TraceAuthorizationDecision.DENY,
    )
    recovery = _event(
        frozen_context,
        case_id=frozen_context.deny_case_id,
        event_id="deny-recovery",
        kind=TraceEventKind.RECOVERY,
        semantic_key="export_state_recovered",
        parent_ids=(authorization.event_id,),
        subject_id=frozen_context.deny_subject_id,
        actor_id=frozen_context.deny_subject_id,
        recorded_at_us=60,
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(recovery, authorization, effect, identity, entry),
        ),
    )

    assert result is not None
    assert result.breakpoint_type is BreakpointType.AUTHORIZATION_LATE
    assert result.amplifier_types == (BreakpointType.COMPENSATION_MASKING,)

def test_fixed_deny_has_no_false_breakpoint(frozen_context: FrozenContext) -> None:
    entry, identity = _base_events(frozen_context)
    authorization = _authorization(
        frozen_context,
        identity.event_id,
        decision=TraceAuthorizationDecision.DENY,
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(authorization, identity, entry),
        ),
        deny_state=ObservedEffect.ABSENT,
    )

    assert result is None

def test_partial_trace_downgrades_to_range(frozen_context: FrozenContext) -> None:
    entry, identity = _base_events(frozen_context)
    effect = _protected(frozen_context, identity.event_id)
    authorization = _authorization(
        frozen_context,
        effect.event_id,
        decision=TraceAuthorizationDecision.DENY,
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(authorization, effect, identity, entry),
            complete=False,
        ),
    )

    assert result is not None
    assert result.precision is BreakpointPrecision.RANGE
    assert result.first_violation_event_id is None
    assert result.range_start_event_id == identity.event_id
    assert result.range_end_event_id == effect.event_id

def test_root_only_partial_trace_reports_violation_only(
    frozen_context: FrozenContext,
) -> None:
    effect = _protected(frozen_context, None)
    authorization = _authorization(
        frozen_context,
        effect.event_id,
        decision=TraceAuthorizationDecision.DENY,
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(authorization, effect),
            complete=False,
        ),
    )

    assert result is not None
    assert result.precision is BreakpointPrecision.VIOLATION_ONLY
    assert result.first_violation_event_id == effect.event_id

def test_confirmed_external_effect_survives_missing_trace(
    frozen_context: FrozenContext,
) -> None:
    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(),
            complete=False,
        ),
    )

    assert result is not None
    assert result.continuity.state.value == "ORPHAN_EFFECT_CONFIRMED"
    assert result.precision is BreakpointPrecision.VIOLATION_ONLY
    assert result.breakpoint_type is None
    assert result.first_violation_event_id is None
    assert "PROTECTED_EFFECT_EVENT_UNAVAILABLE" in result.reason_codes

def test_legal_delegation_does_not_become_authority_expansion(
    frozen_context: FrozenContext,
) -> None:
    actual = frozen_context.allow_subject_id
    entry, identity = _base_events(frozen_context, actual_subject=actual)
    authorization = _authorization(
        frozen_context,
        identity.event_id,
        subject_id=actual,
    )
    delegation = _event(
        frozen_context,
        case_id=frozen_context.deny_case_id,
        event_id="deny-legal-delegation",
        kind=TraceEventKind.DELEGATION,
        semantic_key="export_job_started",
        parent_ids=(authorization.event_id,),
        subject_id=actual,
        actor_id="export-worker",
        credential_source="session-cookie",
        authority_scope=TraceAuthorityScope(
            allowed_action_ids=(frozen_context.action_id,),
            allowed_resource_ids=(frozen_context.resource_id,),
            origin_authorization_event_id=authorization.event_id,
            delegated_from_event_id=authorization.event_id,
        ),
    )
    effect = _protected(
        frozen_context,
        delegation.event_id,
        subject_id=actual,
        actor_id="export-worker",
    )

    result = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(effect, delegation, authorization, identity, entry),
        ),
    )

    assert result is not None
    assert result.breakpoint_type is BreakpointType.IDENTITY_SUBSTITUTION
    assert BreakpointType.AUTHORITY_EXPANSION not in result.amplifier_types

def test_alignment_ignores_random_ids_timestamps_and_input_order(
    frozen_context: FrozenContext,
) -> None:
    first_entry, first_identity = _base_events(frozen_context, prefix="first")
    first_effect = _protected(
        frozen_context, first_identity.event_id, event_id="first-effect"
    )
    first_auth = _authorization(
        frozen_context,
        first_effect.event_id,
        event_id="first-authorization",
        decision=TraceAuthorizationDecision.DENY,
    )
    second_entry, second_identity = _base_events(frozen_context, prefix="second")
    second_effect = _protected(
        frozen_context, second_identity.event_id, event_id="second-effect"
    )
    second_auth = _authorization(
        frozen_context,
        second_effect.event_id,
        event_id="second-authorization",
        decision=TraceAuthorizationDecision.DENY,
    )
    first = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(first_entry, first_identity, first_effect, first_auth),
        ),
        allow_trace=_allow_trace(frozen_context, prefix="control-one"),
    )
    second = _locate(
        frozen_context,
        _trace(
            frozen_context,
            allow=False,
            events=(second_auth, second_effect, second_identity, second_entry),
        ),
        allow_trace=_allow_trace(frozen_context, prefix="control-two"),
    )

    assert first is not None and second is not None
    assert first.breakpoint_type is second.breakpoint_type is BreakpointType.AUTHORIZATION_LATE
    assert first.precision is second.precision is BreakpointPrecision.EXACT
    assert first.orphan_effect_ids == second.orphan_effect_ids
    assert first.reason_codes == second.reason_codes

def test_result_is_strict_frozen_and_all_event_refs_belong_to_deny_trace(
    frozen_context: FrozenContext,
) -> None:
    entry, identity = _base_events(frozen_context)
    effect = _protected(frozen_context, identity.event_id)
    trace = _trace(frozen_context, allow=False, events=(effect, identity, entry))
    result = _locate(frozen_context, trace)

    assert result is not None
    refs = {
        result.last_known_good_event_id,
        result.first_violation_event_id,
        result.range_start_event_id,
        result.range_end_event_id,
        *result.downstream_event_ids,
    }
    assert {item for item in refs if item is not None}.issubset(
        {event.event_id for event in trace.events}
    )
    with pytest.raises(ValidationError):
        result.breakpoint_type = BreakpointType.AUTHORIZATION_LATE
    with pytest.raises(ValidationError):
        BreakpointResult.model_validate(
            {
                **result.model_dump(mode="python"),
                "breakpoint_type": result.breakpoint_type.value,
            },
            strict=True,
        )

pytestmark = [pytest.mark.level2]


def test_causal_graph_keeps_parallel_paths_and_transitive_ancestors():
    from types import SimpleNamespace
    from product.backend.domain.verification.breakpoints.graph import _build_graph
    events=tuple(SimpleNamespace(event_id=name,parent_event_ids=parents) for name,parents in [('request',()),('identity',('request',)),('permission',('identity',)),('effect',('permission','request'))])
    graph=_build_graph(SimpleNamespace(events=events))
    assert graph.ancestors['effect']==frozenset({'request','identity','permission'})
    assert graph.depth['effect']==3
    assert graph.descendants['request']==frozenset({'identity','permission','effect'})
