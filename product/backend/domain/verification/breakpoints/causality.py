# 按已确认事实识别越权因果候选和可证明精度。
from __future__ import annotations

from product.backend.domain.verification.facts import ObservedEffect, SecurityEffectFact
from product.backend.domain.verification.permissions import PermissionContract, PermissionExpectation
from product.backend.domain.verification.trace import ExecutionTrace, TraceAuthorizationDecision, TraceEvent, TraceEventKind
from .graph import _Graph, _event_business_key, _parent_roles
from .models import BreakpointPrecision, BreakpointType, _AllowControlEvent, _AuthorizationScope, _Candidate


def _protected_events(
    graph: _Graph,
    orphan_facts: tuple[SecurityEffectFact, ...],
) -> tuple[TraceEvent, ...]:
    keys = {(fact.effect_id, fact.resource_id) for fact in orphan_facts}
    return tuple(
        sorted(
            (
                event
                for event in graph.by_id.values()
                if event.effect_id is not None
                and any(
                    (event.effect_id, resource_id) in keys
                    for resource_id in event.resource_ids
                )
            ),
            key=lambda event: _event_business_key(event, graph),
        )
    )


def _allow_control_events(
    trace: ExecutionTrace,
    graph: _Graph,
    facts: tuple[SecurityEffectFact, ...],
) -> tuple[_AllowControlEvent, ...]:
    confirmed = {
        (fact.effect_id, fact.resource_id)
        for fact in facts
        if fact.state is ObservedEffect.CONFIRMED
    }
    return tuple(
        _AllowControlEvent(event=event, parent_roles=_parent_roles(event, graph))
        for event in graph.by_id.values()
        if event.effect_id is not None
        and any(
            (event.effect_id, resource_id) in confirmed
            for resource_id in event.resource_ids
        )
        and _has_allow_authorization(event, trace, graph)
    )


def _collect_candidates(
    *,
    scope: _AuthorizationScope,
    trace: ExecutionTrace,
    graph: _Graph,
    protected: tuple[TraceEvent, ...],
    allow_control: tuple[_AllowControlEvent, ...],
) -> tuple[_Candidate, ...]:
    found: dict[tuple[BreakpointType, str], _Candidate] = {}
    reliable_subject = _reliable_actual_subject(trace)
    contract_subject_ids = scope.known_subject_ids
    legal_actions, legal_resources = scope.legal_actions, scope.legal_resources
    for effect_event in protected:
        effect_tuple = (effect_event.event_id,)
        # 已确认后果仍以 E 为真源；成功派发 D 只定位权限检查介入过晚的位置。
        if trace.complete:
            for dispatch in trace.events:
                if (effect_event.effect_id not in dispatch.dispatch_effect_ids
                    or dispatch.event_id not in graph.ancestors[effect_event.event_id]
                    or (dispatch.case_id,dispatch.action_id,dispatch.resource_ids) !=
                        (effect_event.case_id,effect_event.action_id,effect_event.resource_ids)):
                    continue
                relevant = tuple(event for event in trace.events if _relevant_authorization(event,dispatch))
                if not any(event.event_id in graph.ancestors[dispatch.event_id] for event in relevant) and any(
                    event.event_id in graph.descendants[dispatch.event_id]
                    and event.authorization_decision in {TraceAuthorizationDecision.ALLOW,TraceAuthorizationDecision.DENY}
                    for event in relevant):
                    _add_candidate(found,BreakpointType.AUTHORIZATION_LATE,dispatch.event_id,effect_tuple)
        authorizations = tuple(
            event
            for event in graph.by_id.values()
            if _relevant_authorization(event, effect_event)
        )
        before = tuple(
            event
            for event in authorizations
            if event.event_id in graph.ancestors[effect_event.event_id]
        )
        after = tuple(
            event
            for event in authorizations
            if event.event_id in graph.descendants[effect_event.event_id]
        )
        if not authorizations:
            _add_candidate(
                found,
                BreakpointType.AUTHORIZATION_MISSING,
                effect_event.event_id,
                effect_tuple,
            )
        elif after and not before:
            _add_candidate(
                found,
                BreakpointType.AUTHORIZATION_LATE,
                effect_event.event_id,
                effect_tuple,
            )
        elif (
            not any(
                event.authorization_decision is TraceAuthorizationDecision.ALLOW
                for event in before
            )
            and _control_has_normal_path(effect_event, allow_control, graph)
        ):
            _add_candidate(
                found,
                BreakpointType.AUTHORIZATION_BYPASS,
                effect_event.event_id,
                effect_tuple,
            )

        # 目标应用账号与界鉴测试身份可能使用不同命名空间；只有双方都属于冻结合同
        # 的 subject 集合时才允许比较，避免把同一身份的本地账号误判为身份替换。
        if (
            reliable_subject is not None
            and reliable_subject in contract_subject_ids
            and trace.planned_subject_id in contract_subject_ids
            and reliable_subject != trace.planned_subject_id
        ):
            identity_events = tuple(
                event
                for event in graph.by_id.values()
                if event.kind is TraceEventKind.IDENTITY
                and event.subject_id == reliable_subject
                and event.event_id in graph.ancestors[effect_event.event_id]
                and not _has_legal_delegation(event, graph)
                and not _has_legal_delegation(effect_event, graph)
            )
            if identity_events:
                identity = min(
                    identity_events,
                    key=lambda event: _event_business_key(event, graph),
                )
                _add_candidate(
                    found,
                    BreakpointType.IDENTITY_SUBSTITUTION,
                    identity.event_id,
                    effect_tuple,
                )

        for event in graph.by_id.values():
            if event.event_id not in graph.ancestors[effect_event.event_id] and event.event_id != effect_event.event_id:
                continue
            if not _is_background_actor(event, reliable_subject or trace.planned_subject_id):
                continue
            if _exceeds_legal_scope(
                event,
                legal_actions=legal_actions,
                legal_resources=legal_resources,
                invariant_action=scope.invariant_action,
                invariant_resources=scope.invariant_resources,
                trace=trace,
                graph=graph,
            ):
                _add_candidate(
                    found,
                    BreakpointType.AUTHORITY_EXPANSION,
                    event.event_id,
                    effect_tuple,
                )

        recoveries = tuple(
            event
            for event in graph.by_id.values()
            if event.kind is TraceEventKind.RECOVERY
            and event.event_id in graph.descendants[effect_event.event_id]
            and set(event.resource_ids).intersection(effect_event.resource_ids)
        )
        for recovery in recoveries:
            _add_candidate(
                found,
                BreakpointType.COMPENSATION_MASKING,
                recovery.event_id,
                effect_tuple,
            )
    return tuple(found.values())


def _add_candidate(
    found: dict[tuple[BreakpointType, str], _Candidate],
    breakpoint_type: BreakpointType,
    event_id: str,
    orphan_event_ids: tuple[str, ...],
) -> None:
    key = (breakpoint_type, event_id)
    prior = found.get(key)
    merged = tuple(
        sorted({*(prior.orphan_event_ids if prior else ()), *orphan_event_ids})
    )
    found[key] = _Candidate(
        breakpoint_type=breakpoint_type,
        event_id=event_id,
        orphan_event_ids=merged,
        reason_code=f"BREAKPOINT_{breakpoint_type.value}",
    )


def _relevant_authorization(event: TraceEvent, protected: TraceEvent) -> bool:
    if event.kind is not TraceEventKind.AUTHORIZATION:
        return False
    if event.action_id != protected.action_id or not set(event.resource_ids).intersection(protected.resource_ids):
        return False
    scope = event.authority_scope
    if scope.allowed_action_ids and protected.action_id not in scope.allowed_action_ids:
        return False
    if scope.allowed_resource_ids and not set(scope.allowed_resource_ids).intersection(protected.resource_ids):
        return False
    return True


def _has_allow_authorization(
    event: TraceEvent,
    trace: ExecutionTrace,
    graph: _Graph,
) -> bool:
    return any(
        candidate.authorization_decision is TraceAuthorizationDecision.ALLOW
        and _relevant_authorization(candidate, event)
        and candidate.event_id in graph.ancestors[event.event_id]
        for candidate in trace.events
    )


def _control_has_normal_path(
    deny_event: TraceEvent,
    allow_control: tuple[_AllowControlEvent, ...],
    deny_graph: _Graph,
) -> bool:
    deny_parent_roles = _parent_roles(deny_event, deny_graph)
    matches = tuple(
        control
        for control in allow_control
        if control.event.action_id == deny_event.action_id
        and control.event.resource_ids == deny_event.resource_ids
        and control.event.kind is deny_event.kind
        and control.event.effect_id == deny_event.effect_id
    )
    if not matches:
        return False
    semantic_matches = tuple(
        control
        for control in matches
        if control.event.semantic_key == deny_event.semantic_key
    )
    selected = semantic_matches or matches
    return any(
        control.parent_roles != deny_parent_roles
        for control in selected
    )


def _reliable_actual_subject(trace: ExecutionTrace) -> str | None:
    if not trace.complete:
        return None
    subjects = {
        event.subject_id
        for event in trace.events
        if event.kind is TraceEventKind.IDENTITY and event.subject_id is not None
    }
    return next(iter(subjects)) if len(subjects) == 1 else None


def _legal_scope(
    contract: PermissionContract,
    subject_id: str,
) -> tuple[frozenset[str], frozenset[str]]:
    allowed_rules = tuple(
        rule
        for rule in contract.rules
        if rule.subject_id == subject_id
        and rule.expectation is PermissionExpectation.ALLOW
    )
    batch_pairs = tuple(
        (rule.action_id, expectation.resource_id)
        for rule in contract.batch_rules
        if rule.subject_id == subject_id
        for expectation in rule.resource_expectations
        if expectation.expectation is PermissionExpectation.ALLOW
    )
    return (
        frozenset(
            [*(rule.action_id for rule in allowed_rules), *(action for action, _ in batch_pairs)]
        ),
        frozenset(
            [*(rule.resource_id for rule in allowed_rules), *(resource for _, resource in batch_pairs)]
        ),
    )


def _is_background_actor(event: TraceEvent, actual_subject: str) -> bool:
    return event.actor_id is not None and event.actor_id != actual_subject


def _exceeds_legal_scope(
    event: TraceEvent,
    *,
    legal_actions: frozenset[str],
    legal_resources: frozenset[str],
    invariant_action: str,
    invariant_resources: frozenset[str],
    trace: ExecutionTrace,
    graph: _Graph,
) -> bool:
    if _has_legal_delegation(event, graph):
        return False
    scope = event.authority_scope
    if any(
        action_id not in legal_actions or action_id != invariant_action
        for action_id in scope.allowed_action_ids
    ):
        return True
    if any(
        resource_id not in legal_resources or resource_id not in invariant_resources
        for resource_id in scope.allowed_resource_ids
    ):
        return True
    if event.credential_source is None:
        return False
    subject_sources = {
        candidate.credential_source
        for candidate in trace.events
        if candidate.credential_source is not None
        and candidate.event_id in graph.ancestors[event.event_id]
        and candidate.kind in {TraceEventKind.IDENTITY, TraceEventKind.AUTHORIZATION}
    }
    return event.credential_source not in subject_sources


def _has_legal_delegation(
    event: TraceEvent,
    graph: _Graph,
) -> bool:
    """显式委托只在来源授权、因果关系和授权范围都闭合时视为合法。"""

    delegated_from = event.authority_scope.delegated_from_event_id
    if delegated_from is None or delegated_from not in graph.ancestors[event.event_id]:
        return False
    source = graph.by_id[delegated_from]
    if (
        source.kind is not TraceEventKind.AUTHORIZATION
        or source.authorization_decision is not TraceAuthorizationDecision.ALLOW
    ):
        return False
    source_scope = source.authority_scope
    delegated_scope = event.authority_scope
    if (
        not source_scope.allowed_action_ids
        or not source_scope.allowed_resource_ids
        or not set(delegated_scope.allowed_action_ids).issubset(
            source_scope.allowed_action_ids
        )
        or not set(delegated_scope.allowed_resource_ids).issubset(
            source_scope.allowed_resource_ids
        )
    ):
        return False
    return (
        event.action_id in source_scope.allowed_action_ids
        and set(event.resource_ids).issubset(source_scope.allowed_resource_ids)
        and (
            event.credential_source is None
            or event.credential_source == source.credential_source
        )
    )


def _candidate_key(candidate: _Candidate, graph: _Graph) -> tuple[object, ...]:
    event = graph.by_id[candidate.event_id]
    return (
        graph.depth[candidate.event_id],
        event.action_id,
        event.resource_ids,
        event.kind.value,
        event.effect_id or "",
        _parent_roles(event, graph),
        event.semantic_key,
        candidate.breakpoint_type.value,
        candidate.event_id,
    )


def _precision(
    *,
    allow_trace: ExecutionTrace,
    deny_trace: ExecutionTrace,
    primary_event: TraceEvent,
    direct_parents: tuple[str, ...],
    ambiguous_primary: bool,
) -> tuple[BreakpointPrecision, dict[str, str | None], tuple[str, ...]]:
    last_good = direct_parents[0] if len(direct_parents) == 1 else None
    if allow_trace.complete and deny_trace.complete and not ambiguous_primary:
        return (
            BreakpointPrecision.EXACT,
            {
                "last_known_good_event_id": last_good,
                "first_violation_event_id": primary_event.event_id,
            },
            ("EXACT_BREAKPOINT",),
        )
    if last_good is not None:
        return (
            BreakpointPrecision.RANGE,
            {
                "last_known_good_event_id": last_good,
                "range_start_event_id": last_good,
                "range_end_event_id": primary_event.event_id,
            },
            ("BREAKPOINT_RANGE_ONLY", "TRACE_EVIDENCE_INCOMPLETE"),
        )
    return (
        BreakpointPrecision.VIOLATION_ONLY,
        {"first_violation_event_id": primary_event.event_id},
        ("TRACE_EVIDENCE_INCOMPLETE", "VIOLATION_ONLY"),
    )


def _amplifiers(
    primary: _Candidate,
    candidates: list[_Candidate],
    graph: _Graph,
) -> tuple[BreakpointType, ...]:
    types = {
        candidate.breakpoint_type
        for candidate in candidates
        if candidate.breakpoint_type is not primary.breakpoint_type
        and candidate.event_id in graph.descendants[primary.event_id]
    }
    return tuple(sorted(types, key=lambda item: item.value))
