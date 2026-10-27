# 验证冻结输入归属并编排权限断裂诊断。
from __future__ import annotations

import re
from product.backend.domain.verification.differential import DifferentialExperimentPlan, PermissionTwin
from product.backend.domain.verification.continuity import AuthorizationContinuityAssessment, AuthorizationContinuityState, assess_authorization_continuity, assess_check_authorization_continuity
from product.backend.domain.verification.checks import CheckDecisionInput
from product.protocols.checks.execution_request import ExecutionAction, ExecutionTwin
from product.protocols.checks.check_runtime import CheckIdentity
from product.backend.domain.verification.facts import ObservedEffect, SecurityEffectFact
from product.backend.domain.verification.permissions import PermissionContract, PermissionExpectation
from product.backend.domain.verification.trace import ExecutionTrace
from .causality import _allow_control_events, _amplifiers, _candidate_key, _collect_candidates, _legal_scope, _precision, _protected_events
from .graph import _Graph, _build_graph, _downstream_events, _event_business_key
from .models import BreakpointPrecision, BreakpointResult, _AuthorizationScope, _LocatedEffect, _PUBLIC_ID


class BreakpointLocator:
    """分析一个已运行 DENY twin；本类不拥有任何执行或现场读取能力。"""

    def locate_current(
        self, *, action: ExecutionAction, twin: ExecutionTwin,
        allow_facts: CheckDecisionInput, deny_facts: CheckDecisionInput,
        allow_trace: ExecutionTrace | None, deny_trace: ExecutionTrace | None,
        identities: tuple[CheckIdentity, ...], trace_namespace: str | None,
        allow_evidence_refs: tuple[str, ...], deny_evidence_refs: tuple[str, ...],
    ) -> BreakpointResult | None:
        """仅诊断当前冻结孪生的已归因禁止效果；引用集合必须分别来自同 Run 的对应 Case。"""
        if (twin not in action.twins or allow_facts.case not in action.cases
            or deny_facts.case not in action.cases
            or (allow_facts.case.case_id, deny_facts.case.case_id) != (twin.allow_case_id, twin.deny_case_id)):
            raise ValueError("breakpoint inputs must belong to one frozen twin")
        continuity = assess_check_authorization_continuity(action, deny_facts)
        if continuity.state is not AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED:
            return None
        deny_refs = _published_refs(deny_evidence_refs)
        allow_refs = _published_refs(allow_evidence_refs)
        if set(deny_refs).intersection(allow_refs):
            raise ValueError("breakpoint evidence must remain case scoped")
        identities_by_id = {item.identity_id: item for item in identities}
        if len(identities_by_id) != len(identities):
            raise ValueError("duplicate frozen identity")
        for facts, trace, refs in ((allow_facts, allow_trace, allow_refs), (deny_facts, deny_trace, deny_refs)):
            if trace is None:
                continue
            identity = identities_by_id.get(facts.case.subject_test_identity_id)
            mapping = identity.verification if identity is not None else None
            expected_subject = (mapping.expected_application_subject_id
                if mapping is not None and mapping.namespace == trace_namespace else facts.case.subject_test_identity_id)
            if (trace.case_id != facts.case.case_id or trace.action_id != action.action_id
                or trace.planned_subject_id != expected_subject
                or any(not set(event.evidence_refs).issubset(refs) for event in trace.events)
                or any(not set(event.resource_ids).issubset({facts.case.resource_id}) for event in trace.events)):
                raise ValueError("trace is outside the frozen published case")
        if allow_trace is None or deny_trace is None:
            return _violation_only_result(continuity=continuity, evidence_refs=deny_refs,
                reason_code="PROTECTED_EFFECT_EVENT_UNAVAILABLE")
        # 只有冻结身份指纹、同一应用命名空间及一对一映射同时成立，才比较真实账号。
        subject_ids = set()
        legal_resources = set()
        mappings = {}
        for case in action.cases:
            identity = identities_by_id.get(case.subject_test_identity_id)
            if identity is None or identity.identity_fingerprint != case.subject_identity_fingerprint:
                continue
            verification = identity.verification
            if verification is None or verification.namespace != trace_namespace:
                continue
            subject = verification.expected_application_subject_id
            mappings.setdefault(subject, set()).add(identity.identity_id)
            subject_ids.add(subject)
            if subject == deny_trace.planned_subject_id and case.permission.expectation == "ALLOW":
                legal_resources.add(case.resource_id)
        subject_ids = {subject for subject in subject_ids if len(mappings[subject]) == 1}
        scope = _AuthorizationScope(frozenset(subject_ids),
            frozenset({action.action_id}) if legal_resources else frozenset(),
            frozenset(legal_resources), action.action_id, frozenset({deny_facts.case.resource_id}))
        orphan_facts = tuple(_LocatedEffect(item.effect_id, item.resource_id, ObservedEffect.CONFIRMED)
                             for item in continuity.confirmed_effects)
        allow_effects = ()
        if allow_facts.actual_identity == "MATCH" and allow_facts.run_correlated and allow_facts.resource_correlated:
            required = {proof.proof_fingerprint for proof in allow_facts.case.proof_requirements if proof.level == "VERDICT_REQUIRED"}
            allow_effects = tuple(_LocatedEffect(item.effect_id, allow_facts.case.resource_id, ObservedEffect.CONFIRMED)
                for item in allow_facts.effects if item.proof_fingerprint in required and item.state == "CONFIRMED"
                and item.complete and item.reliable and item.correlated and item.authoritative)
        return _locate_frozen_effects(continuity=continuity, allow_trace=allow_trace, deny_trace=deny_trace,
            orphan_facts=orphan_facts, allow_effect_facts=allow_effects, published_refs=deny_refs, scope=scope)

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

        legal_actions, legal_resources = _legal_scope(contract, deny_trace.planned_subject_id)
        scope = _AuthorizationScope(
            frozenset(subject.subject_id for subject in contract.subjects),
            legal_actions, legal_resources, twin.invariant.action_id,
            frozenset(twin.invariant.resource_ids),
        )
        return _locate_frozen_effects(continuity=continuity, allow_trace=allow_trace,
            deny_trace=deny_trace, orphan_facts=orphan_facts,
            allow_effect_facts=allow_effect_facts, published_refs=published_refs, scope=scope)


def _locate_frozen_effects(*, continuity, allow_trace, deny_trace, orphan_facts,
                          allow_effect_facts, published_refs, scope):
    """共享因果图与精度算法；调用入口负责冻结权限、事实和已发布引用的边界校验。"""
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
        scope=scope,
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
