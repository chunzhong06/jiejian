# 被动权限断裂定位：只从冻结的差分计划、Trace 与已发布效果事实还原首个可证明断裂。

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from product.backend.core.verification.differential import (
    DifferentialExperimentPlan,
    PermissionTwin,
)
from product.backend.core.verification.continuity import (
    AuthorizationContinuityAssessment,
    AuthorizationContinuityState,
    assess_authorization_continuity,
)
from product.backend.core.verification.facts import ObservedEffect, SecurityEffectFact
from product.backend.core.verification.permissions import (
    PermissionContract,
    PermissionExpectation,
)
from product.backend.core.verification.trace import (
    ExecutionTrace,
    TraceAuthorizationDecision,
    TraceEvent,
    TraceEventKind,
)


_PUBLIC_ID = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}$"
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class BreakpointType(StrEnum):
    AUTHORIZATION_MISSING = "AUTHORIZATION_MISSING"
    AUTHORIZATION_LATE = "AUTHORIZATION_LATE"
    AUTHORIZATION_BYPASS = "AUTHORIZATION_BYPASS"
    IDENTITY_SUBSTITUTION = "IDENTITY_SUBSTITUTION"
    AUTHORITY_EXPANSION = "AUTHORITY_EXPANSION"
    COMPENSATION_MASKING = "COMPENSATION_MASKING"


class BreakpointPrecision(StrEnum):
    EXACT = "EXACT"
    RANGE = "RANGE"
    VIOLATION_ONLY = "VIOLATION_ONLY"


class _BreakpointModel(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )


class BreakpointResult(_BreakpointModel):
    case_id: str = Field(pattern=_PUBLIC_ID)
    action_id: str = Field(pattern=_PUBLIC_ID)
    breakpoint_type: BreakpointType | None
    precision: BreakpointPrecision
    last_known_good_event_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    first_violation_event_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    range_start_event_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    range_end_event_id: str | None = Field(default=None, pattern=_PUBLIC_ID)
    continuity: AuthorizationContinuityAssessment
    orphan_effect_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    downstream_event_ids: tuple[str, ...] = Field(default=(), max_length=512)
    amplifier_types: tuple[BreakpointType, ...] = Field(default=(), max_length=5)
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=128)
    reason_codes: tuple[str, ...] = Field(min_length=1, max_length=32)

    @field_validator(
        "orphan_effect_ids",
        "downstream_event_ids",
        "evidence_refs",
    )
    @classmethod
    def validate_unique_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("breakpoint ID references must be unique")
        return values

    @field_validator("amplifier_types")
    @classmethod
    def validate_amplifiers(
        cls, values: tuple[BreakpointType, ...]
    ) -> tuple[BreakpointType, ...]:
        if len(set(values)) != len(values):
            raise ValueError("breakpoint amplifier types must be unique")
        return values

    @field_validator("reason_codes")
    @classmethod
    def validate_reason_codes(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values) or any(
            _REASON_CODE.fullmatch(value) is None for value in values
        ):
            raise ValueError("breakpoint reason codes must be stable unique tokens")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_precision_shape(self) -> BreakpointResult:
        if (
            self.continuity.state
            is not AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED
            or self.continuity.case_id != self.case_id
            or self.continuity.action_id != self.action_id
            or set(self.orphan_effect_ids)
            != {item.effect_id for item in self.continuity.confirmed_effects}
        ):
            raise ValueError("breakpoint must reuse its confirmed continuity assessment")
        if self.breakpoint_type is not None and self.breakpoint_type in self.amplifier_types:
            raise ValueError("primary breakpoint cannot also be an amplifier")
        if self.precision is BreakpointPrecision.EXACT:
            if self.breakpoint_type is None or self.first_violation_event_id is None:
                raise ValueError("EXACT breakpoint requires a type and first violation event")
            if self.range_start_event_id is not None or self.range_end_event_id is not None:
                raise ValueError("EXACT breakpoint cannot carry a range")
        elif self.precision is BreakpointPrecision.RANGE:
            if (
                self.breakpoint_type is None
                or self.first_violation_event_id is not None
                or self.range_start_event_id is None
                or self.range_end_event_id is None
            ):
                raise ValueError("RANGE breakpoint requires only range boundaries")
        elif (
            self.last_known_good_event_id is not None
            or self.range_start_event_id is not None
            or self.range_end_event_id is not None
        ):
            raise ValueError("VIOLATION_ONLY cannot claim a stable trace boundary")
        return self


@dataclass(frozen=True, slots=True)
class _Graph:
    by_id: dict[str, TraceEvent]
    parents: dict[str, frozenset[str]]
    children: dict[str, frozenset[str]]
    ancestors: dict[str, frozenset[str]]
    descendants: dict[str, frozenset[str]]
    depth: dict[str, int]


@dataclass(frozen=True, slots=True)
class _Candidate:
    breakpoint_type: BreakpointType
    event_id: str
    orphan_event_ids: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True, slots=True)
class _AllowControlEvent:
    event: TraceEvent
    parent_roles: tuple[str, ...]


class BreakpointLocator:
    """分析一个已运行 DENY twin；本类不拥有任何执行或现场读取能力。"""

    def locate(
        self,
        *,
        contract: PermissionContract,
        differential_plan: DifferentialExperimentPlan,
        allow_trace: ExecutionTrace,
        deny_trace: ExecutionTrace,
        allow_effect_facts: tuple[SecurityEffectFact, ...],
        deny_effect_facts: tuple[SecurityEffectFact, ...],
        evidence_refs: tuple[str, ...],
    ) -> BreakpointResult | None:
        twin = _resolve_twin(differential_plan, allow_trace, deny_trace)
        _validate_frozen_scope(contract, twin, allow_trace, deny_trace)
        published_refs = _published_refs(evidence_refs)
        continuity = assess_authorization_continuity(
            contract,
            twin,
            deny_effect_facts,
        )
        if continuity.state is not AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED:
            return None
        confirmed_keys = {
            (item.effect_id, item.resource_id)
            for item in continuity.confirmed_effects
        }
        orphan_facts = tuple(
            fact
            for fact in deny_effect_facts
            if (fact.effect_id, fact.resource_id) in confirmed_keys
        )

        graph = _build_graph(deny_trace)
        allow_graph = _build_graph(allow_trace)
        protected = _protected_events(graph, orphan_facts)
        if not protected:
            return _violation_only_result(
                continuity=continuity,
                evidence_refs=published_refs,
                reason_code="PROTECTED_EFFECT_EVENT_UNAVAILABLE",
            )
        allow_control = _allow_control_events(
            allow_trace,
            allow_graph,
            allow_effect_facts,
        )
        candidates = _collect_candidates(
            contract=contract,
            twin=twin,
            trace=deny_trace,
            graph=graph,
            protected=protected,
            allow_control=allow_control,
        )
        if not candidates:
            return _violation_only_result(
                continuity=continuity,
                evidence_refs=published_refs,
                reason_code="BREAKPOINT_TRACE_UNRESOLVED",
            )

        causal_first = tuple(
            candidate
            for candidate in candidates
            if not any(
                other.event_id in graph.ancestors[candidate.event_id]
                for other in candidates
                if other is not candidate
            )
        )
        primary = min(causal_first, key=lambda item: _candidate_key(item, graph))
        ordered = sorted(candidates, key=lambda item: _candidate_key(item, graph))
        primary_event = graph.by_id[primary.event_id]
        direct_parents = tuple(
            sorted(
                graph.parents[primary.event_id],
                key=lambda event_id: _event_business_key(graph.by_id[event_id], graph),
            )
        )
        ambiguous_primary = len(causal_first) > 1
        precision, boundary_fields, precision_reasons = _precision(
            allow_trace=allow_trace,
            deny_trace=deny_trace,
            primary_event=primary_event,
            direct_parents=direct_parents,
            ambiguous_primary=ambiguous_primary,
        )
        downstream = _downstream_events(primary, ordered, protected, graph)
        amplifiers = _amplifiers(primary, ordered, graph)
        result_refs = tuple(
            sorted(
                {
                    *published_refs,
                    *primary_event.evidence_refs,
                    *(
                        evidence_ref
                        for event_id in primary.orphan_event_ids
                        for evidence_ref in graph.by_id[event_id].evidence_refs
                    ),
                }
            )
        )
        if not result_refs:
            raise ValueError("breakpoint requires a published Evidence reference")
        result = BreakpointResult(
            case_id=deny_trace.case_id,
            action_id=deny_trace.action_id,
            breakpoint_type=primary.breakpoint_type,
            precision=precision,
            continuity=continuity,
            orphan_effect_ids=tuple(sorted({fact.effect_id for fact in orphan_facts})),
            downstream_event_ids=downstream,
            amplifier_types=amplifiers,
            evidence_refs=result_refs,
            reason_codes=tuple(
                {
                    "CONFIRMED_ORPHAN_EFFECT",
                    primary.reason_code,
                    *precision_reasons,
                }
            ),
            **boundary_fields,
        )
        _validate_result_event_refs(result, graph)
        return result


def _violation_only_result(
    *,
    continuity: AuthorizationContinuityAssessment,
    evidence_refs: tuple[str, ...],
    reason_code: str,
) -> BreakpointResult:
    """效果已确认但 Trace 无稳定节点时，只声明违规存在，不虚构因果事件。"""

    return BreakpointResult(
        case_id=continuity.case_id,
        action_id=continuity.action_id,
        breakpoint_type=None,
        precision=BreakpointPrecision.VIOLATION_ONLY,
        continuity=continuity,
        orphan_effect_ids=tuple(
            sorted({item.effect_id for item in continuity.confirmed_effects})
        ),
        evidence_refs=evidence_refs,
        reason_codes=(
            "CONFIRMED_ORPHAN_EFFECT",
            reason_code,
            "TRACE_EVIDENCE_INCOMPLETE",
            "VIOLATION_ONLY",
        ),
    )


def _resolve_twin(
    plan: DifferentialExperimentPlan,
    allow_trace: ExecutionTrace,
    deny_trace: ExecutionTrace,
) -> PermissionTwin:
    matches = tuple(
        twin
        for twin in plan.twins
        if twin.allow_case.case_id == allow_trace.case_id
        and twin.deny_case.case_id == deny_trace.case_id
    )
    if len(matches) != 1:
        raise ValueError("traces must identify exactly one frozen differential twin")
    return matches[0]


def _validate_frozen_scope(
    contract: PermissionContract,
    twin: PermissionTwin,
    allow_trace: ExecutionTrace,
    deny_trace: ExecutionTrace,
) -> None:
    if any(
        value is not PermissionExpectation.ALLOW
        for value in twin.allow_case.expectations
    ) or any(
        value is not PermissionExpectation.DENY
        for value in twin.deny_case.expectations
    ):
        raise ValueError("breakpoint locator requires an ALLOW/DENY twin")
    if allow_trace.action_id != twin.invariant.action_id or deny_trace.action_id != twin.invariant.action_id:
        raise ValueError("trace action does not match the frozen twin")
    if (
        allow_trace.planned_subject_id != twin.allow_case.subject_id
        or deny_trace.planned_subject_id != twin.deny_case.subject_id
    ):
        raise ValueError("trace planned subject does not match the frozen twin")
    invariant_resources = set(twin.invariant.resource_ids)
    if any(
        not set(event.resource_ids).issubset(invariant_resources)
        for trace in (allow_trace, deny_trace)
        for event in trace.events
    ):
        raise ValueError("trace event resource is outside the frozen twin")
    action_ids = {action.action_id for action in contract.actions}
    resource_ids = {resource.resource_id for resource in contract.resources}
    subject_ids = {subject.subject_id for subject in contract.subjects}
    if twin.invariant.action_id not in action_ids or any(
        resource_id not in resource_ids for resource_id in twin.invariant.resource_ids
    ):
        raise ValueError("frozen twin is outside the contract action or resource scope")
    if allow_trace.planned_subject_id not in subject_ids or deny_trace.planned_subject_id not in subject_ids:
        raise ValueError("trace planned subject is outside the frozen contract")


def _published_refs(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError("published Evidence references must be unique")
    if any(re.fullmatch(_PUBLIC_ID, value) is None for value in values):
        raise ValueError("published Evidence reference is invalid")
    return tuple(sorted(values))


def _build_graph(trace: ExecutionTrace) -> _Graph:
    by_id = {event.event_id: event for event in trace.events}
    parents = {
        event_id: frozenset(event.parent_event_ids) for event_id, event in by_id.items()
    }
    mutable_children = {event_id: set() for event_id in by_id}
    for event_id, parent_ids in parents.items():
        for parent_id in parent_ids:
            mutable_children[parent_id].add(event_id)
    children = {
        event_id: frozenset(child_ids)
        for event_id, child_ids in mutable_children.items()
    }
    ancestor_cache: dict[str, frozenset[str]] = {}
    descendant_cache: dict[str, frozenset[str]] = {}
    depth_cache: dict[str, int] = {}

    def ancestors(event_id: str) -> frozenset[str]:
        if event_id not in ancestor_cache:
            ancestor_cache[event_id] = frozenset(
                parent_id
                for direct_parent in parents[event_id]
                for parent_id in (direct_parent, *ancestors(direct_parent))
            )
        return ancestor_cache[event_id]

    def descendants(event_id: str) -> frozenset[str]:
        if event_id not in descendant_cache:
            descendant_cache[event_id] = frozenset(
                child_id
                for direct_child in children[event_id]
                for child_id in (direct_child, *descendants(direct_child))
            )
        return descendant_cache[event_id]

    def depth(event_id: str) -> int:
        if event_id not in depth_cache:
            depth_cache[event_id] = (
                0
                if not parents[event_id]
                else 1 + max(depth(parent_id) for parent_id in parents[event_id])
            )
        return depth_cache[event_id]

    for event_id in by_id:
        ancestors(event_id)
        descendants(event_id)
        depth(event_id)
    return _Graph(
        by_id=by_id,
        parents=parents,
        children=children,
        ancestors=ancestor_cache,
        descendants=descendant_cache,
        depth=depth_cache,
    )


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
    contract: PermissionContract,
    twin: PermissionTwin,
    trace: ExecutionTrace,
    graph: _Graph,
    protected: tuple[TraceEvent, ...],
    allow_control: tuple[_AllowControlEvent, ...],
) -> tuple[_Candidate, ...]:
    found: dict[tuple[BreakpointType, str], _Candidate] = {}
    reliable_subject = _reliable_actual_subject(trace)
    legal_actions, legal_resources = _legal_scope(
        contract, trace.planned_subject_id
    )
    for effect_event in protected:
        effect_tuple = (effect_event.event_id,)
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

        if reliable_subject is not None and reliable_subject != trace.planned_subject_id:
            identity_events = tuple(
                event
                for event in graph.by_id.values()
                if event.kind is TraceEventKind.IDENTITY
                and event.subject_id == reliable_subject
                and event.event_id in graph.ancestors[effect_event.event_id]
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
                invariant_action=twin.invariant.action_id,
                invariant_resources=frozenset(twin.invariant.resource_ids),
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


def _parent_roles(event: TraceEvent, graph: _Graph) -> tuple[str, ...]:
    return tuple(
        sorted(graph.by_id[parent_id].kind.value for parent_id in event.parent_event_ids)
    )


def _event_business_key(event: TraceEvent, graph: _Graph) -> tuple[object, ...]:
    return (
        graph.depth[event.event_id],
        event.action_id,
        event.resource_ids,
        event.kind.value,
        event.effect_id or "",
        _parent_roles(event, graph),
        event.semantic_key,
        event.event_id,
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


def _downstream_events(
    primary: _Candidate,
    candidates: list[_Candidate],
    protected: tuple[TraceEvent, ...],
    graph: _Graph,
) -> tuple[str, ...]:
    related = {
        event_id
        for event_id in graph.descendants[primary.event_id]
        if any(
            event_id == event.event_id
            or event_id in graph.ancestors[event.event_id]
            or event_id in graph.descendants[event.event_id]
            for event in protected
        )
    }
    related.update(
        candidate.event_id
        for candidate in candidates
        if candidate.event_id in graph.descendants[primary.event_id]
    )
    return tuple(
        sorted(
            related,
            key=lambda event_id: _event_business_key(graph.by_id[event_id], graph),
        )
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


def _validate_result_event_refs(result: BreakpointResult, graph: _Graph) -> None:
    references = {
        result.last_known_good_event_id,
        result.first_violation_event_id,
        result.range_start_event_id,
        result.range_end_event_id,
        *result.downstream_event_ids,
    }
    if any(reference is not None and reference not in graph.by_id for reference in references):
        raise ValueError("breakpoint event reference is outside the current Trace")


__all__ = [
    "BreakpointLocator",
    "BreakpointPrecision",
    "BreakpointResult",
    "BreakpointType",
]
