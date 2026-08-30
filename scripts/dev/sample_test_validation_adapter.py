# validation 薄适配层：只把公开 fixture 事实构造成正式 Contract、Twin、Fact 与 Trace，不判断安全结论。

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping

from product.backend.core.verification.differential import (
    DifferentialExperimentPlan,
    PermissionMutationDescriptor,
    PermissionTwin,
    TwinInvariantSpecification,
)
from product.backend.core.verification.facts import SecurityEffectFact
from product.backend.core.verification.permissions import (
    ActionDefinition,
    CoverageDimension,
    PermissionContext,
    PermissionContract,
    PermissionExpectation,
    PermissionRule,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinition,
    SecurityEffectDefinition,
    SecurityEffectKind,
    SubjectDefinition,
    permission_model_sha256,
)
from product.backend.core.verification.permissions.coverage import (
    PermissionMutationCase,
    RetentionReason,
)
from product.backend.core.verification.trace import (
    ExecutionTrace,
    TraceAuthorityScope,
    TraceAuthorizationDecision,
    TraceCorrelationKind,
    TraceEvent,
    TraceEventKind,
)
from sample_test_registry import PublicValidationCase


_TRACE_KIND_ALIASES = {
    "FEATURE": TraceEventKind.ENTRY,
    "PROTECTED_EFFECT": TraceEventKind.FINAL_EFFECT,
}


@dataclass(frozen=True, slots=True)
class ValidationDomainBundle:
    """公开验证事实的正式领域模型集合；调用方负责交给生产算法。"""

    contract: PermissionContract
    plan: DifferentialExperimentPlan
    twin: PermissionTwin
    allow_trace: ExecutionTrace
    deny_trace: ExecutionTrace
    allow_effect_facts: tuple[SecurityEffectFact, ...]
    deny_effect_facts: tuple[SecurityEffectFact, ...]
    evidence_refs: tuple[str, ...]


def build_validation_domain_bundle(
    case: PublicValidationCase,
    *,
    allow_trace_records: tuple[Mapping[str, object], ...],
    deny_trace_records: tuple[Mapping[str, object], ...],
    allow_trace_complete: bool,
    deny_trace_complete: bool,
    allow_effect_fact: SecurityEffectFact,
    deny_effect_fact: SecurityEffectFact,
) -> ValidationDomainBundle:
    """只按公开字段完成结构转换，不读取 mode、case_id 答案或 private oracle。"""

    contract = _contract(case)
    twin, plan = _differential(case)
    allow_ref = "validation-allow-evidence"
    deny_ref = "validation-deny-evidence"
    return ValidationDomainBundle(
        contract=contract,
        plan=plan,
        twin=twin,
        allow_trace=_trace(
            case,
            records=allow_trace_records,
            case_id=twin.allow_case.case_id,
            planned_subject_id=twin.allow_case.subject_id,
            role="allow",
            complete=allow_trace_complete,
            evidence_ref=allow_ref,
        ),
        deny_trace=_trace(
            case,
            records=deny_trace_records,
            case_id=twin.deny_case.case_id,
            planned_subject_id=twin.deny_case.subject_id,
            role="deny",
            complete=deny_trace_complete,
            evidence_ref=deny_ref,
        ),
        allow_effect_facts=(allow_effect_fact,),
        deny_effect_facts=(deny_effect_fact,),
        evidence_refs=(allow_ref, deny_ref),
    )


def _contract(case: PublicValidationCase) -> PermissionContract:
    effect_kind = SecurityEffectKind(str(case.observation_config["effect_kind"]))
    allow_relation = "validation-allow-link"
    deny_relation = "validation-deny-link"
    required_channel = str(case.observation_config["required_channel"])
    protected_fields = ("record",) if effect_kind is SecurityEffectKind.DATA_DISCLOSURE else ()
    return PermissionContract(
        contract_id="validation-contract",
        version=1,
        role_ids=("validation-allow-role", "validation-deny-role"),
        workflow_states=("ACTIVE",),
        subjects=(
            SubjectDefinition(
                subject_id=case.allow_control_identity,
                roles=("validation-allow-role",),
                tenant_id="tenant-alpha",
            ),
            SubjectDefinition(
                subject_id=case.identity,
                roles=("validation-deny-role",),
                tenant_id="tenant-alpha",
            ),
        ),
        effects=(
            SecurityEffectDefinition(
                effect_id=case.protected_effects[0],
                kind=effect_kind,
                resource_type="validation-resource",
                protected_fields=protected_fields,
            ),
        ),
        actions=(
            ActionDefinition(
                action_id=case.business_action,
                effect_ids=(case.protected_effects[0],),
            ),
        ),
        resources=(
            ResourceDefinition(
                resource_id=case.resource,
                resource_type="validation-resource",
                tenant_id="tenant-alpha",
                owner_subject_id=case.allow_control_identity,
                workflow_state="ACTIVE",
            ),
        ),
        relations=(
            RelationFact(
                relation_id=allow_relation,
                relation=RelationType.OWNS,
                source=RelationEndpoint(
                    endpoint_type="subject",
                    endpoint_id=case.allow_control_identity,
                ),
                target=RelationEndpoint(
                    endpoint_type="resource",
                    endpoint_id=case.resource,
                ),
            ),
            RelationFact(
                relation_id=deny_relation,
                relation=RelationType.MEMBER_OF,
                source=RelationEndpoint(
                    endpoint_type="subject",
                    endpoint_id=case.identity,
                ),
                target=RelationEndpoint(
                    endpoint_type="resource",
                    endpoint_id=case.resource,
                ),
            ),
        ),
        rules=(
            PermissionRule(
                rule_id="validation-allow-rule",
                subject_id=case.allow_control_identity,
                action_id=case.business_action,
                resource_id=case.resource,
                relation_path=(allow_relation,),
                context=PermissionContext(
                    tenant_ids=("tenant-alpha",),
                    resource_ids=(case.resource,),
                ),
                expectation=PermissionExpectation.ALLOW,
                required_observations=(required_channel,),
                coverage_dimensions=(CoverageDimension.RELATION,),
            ),
            PermissionRule(
                rule_id="validation-deny-rule",
                subject_id=case.identity,
                action_id=case.business_action,
                resource_id=case.resource,
                relation_path=(deny_relation,),
                context=PermissionContext(
                    tenant_ids=("tenant-alpha",),
                    resource_ids=(case.resource,),
                ),
                expectation=PermissionExpectation.DENY,
                required_observations=(required_channel,),
                coverage_dimensions=(CoverageDimension.RELATION,),
            ),
        ),
    )


def _differential(
    case: PublicValidationCase,
) -> tuple[PermissionTwin, DifferentialExperimentPlan]:
    allow = _mutation_case(
        case,
        subject_id=case.allow_control_identity,
        expectation=PermissionExpectation.ALLOW,
        relation_id="validation-allow-link",
        role="allow",
    )
    deny = _mutation_case(
        case,
        subject_id=case.identity,
        expectation=PermissionExpectation.DENY,
        relation_id="validation-deny-link",
        role="deny",
    )
    mutation = PermissionMutationDescriptor(
        dimension=CoverageDimension.RELATION,
        changed_fields=("relation_paths", "subject_id"),
        allow_value_fingerprint=permission_model_sha256(
            {"relation_paths": allow.relation_paths, "subject_id": allow.subject_id}
        ),
        deny_value_fingerprint=permission_model_sha256(
            {"relation_paths": deny.relation_paths, "subject_id": deny.subject_id}
        ),
    )
    invariant_hash = hashlib.sha256(
        f"{case.business_action}|{case.resource}|{case.protected_effects[0]}".encode()
    ).hexdigest()
    invariant = TwinInvariantSpecification(
        action_id=case.business_action,
        resource_ids=(case.resource,),
        workflow_fingerprint=invariant_hash,
        effect_fingerprint=invariant_hash,
        observer_fingerprint=invariant_hash,
        baseline_fingerprint=invariant_hash,
        normalization_version="validation-adapter-v1",
    )
    twin_payload = {
        "source_rule_id": "validation-deny-rule",
        "allow_case": allow,
        "deny_case": deny,
        "varied_dimension": CoverageDimension.RELATION,
        "mutation": mutation,
        "invariant": invariant,
    }
    twin_fingerprint = permission_model_sha256(twin_payload)
    twin = PermissionTwin(
        **twin_payload,
        twin_id=f"twin-{twin_fingerprint[:32]}",
        twin_fingerprint=twin_fingerprint,
    )
    body = {
        "coverage_plan_fingerprint": invariant_hash,
        "twins": (twin,),
        "gaps": (),
    }
    plan_fingerprint = permission_model_sha256(body)
    plan = DifferentialExperimentPlan(
        **body,
        differential_plan_id=f"dplan-{plan_fingerprint[:32]}",
        differential_fingerprint=plan_fingerprint,
    )
    return twin, plan


def _mutation_case(
    case: PublicValidationCase,
    *,
    subject_id: str,
    expectation: PermissionExpectation,
    relation_id: str,
    role: str,
) -> PermissionMutationCase:
    fingerprint = hashlib.sha256(f"{case.case_id}|{role}".encode()).hexdigest()
    return PermissionMutationCase(
        case_id=f"case-{fingerprint[:32]}",
        fingerprint=fingerprint,
        finding_pre_identity=hashlib.sha256(
            f"{case.case_id}|{role}|finding".encode()
        ).hexdigest(),
        source_rule_ids=(f"validation-{role}-rule",),
        dimensions=(CoverageDimension.RELATION,),
        retention_reason=RetentionReason.EXPLICIT_DENY_RISK,
        subject_id=subject_id,
        action_id=case.business_action,
        resource_ids=(case.resource,),
        expectations=(expectation,),
        relation_paths=((relation_id,),),
        context=PermissionContext(
            tenant_ids=("tenant-alpha",),
            resource_ids=(case.resource,),
        ),
        required_observations=(str(case.observation_config["required_channel"]),),
    )


def _trace(
    case: PublicValidationCase,
    *,
    records: tuple[Mapping[str, object], ...],
    case_id: str,
    planned_subject_id: str,
    role: str,
    complete: bool,
    evidence_ref: str,
) -> ExecutionTrace:
    prepared = tuple(
        sorted(
            (record for record in records if record.get("semantic_key") is not None),
            key=lambda record: int(record.get("sequence") or 0),
        )
    )
    event_ids = tuple(
        str(record.get("event_id") or f"validation-{role}-{index}")
        for index, record in enumerate(prepared, start=1)
    )
    known_ids = set(event_ids)
    events: list[TraceEvent] = []
    previous_id: str | None = None
    effect_key = str(case.observation_config["trace_effect_key"])
    for index, (record, event_id) in enumerate(
        zip(prepared, event_ids, strict=True),
        start=1,
    ):
        raw_kind = str(record.get("kind") or "")
        kind = _TRACE_KIND_ALIASES.get(raw_kind)
        if kind is None:
            kind = TraceEventKind(raw_kind)
        raw_parent = record.get("parent_event_id")
        parent_id = (
            str(raw_parent)
            if raw_parent is not None and str(raw_parent) in known_ids
            else previous_id
        )
        raw_subject = record.get("subject_id", record.get("identity"))
        raw_actor = record.get("actor_id", raw_subject)
        subject_id = planned_subject_id if raw_subject is not None else None
        raw_decision = record.get("authorization_decision")
        decision = (
            TraceAuthorizationDecision(str(raw_decision))
            if raw_decision is not None
            else None
        )
        origin_ref = _known_reference(record.get("origin_authorization_event_id"), known_ids)
        delegated_ref = _known_reference(record.get("delegated_from_event_id"), known_ids)
        if kind is TraceEventKind.DELEGATION and delegated_ref is None:
            delegated_ref = parent_id
        # source_component 不是权限主体；只有显式委派事实才把后台 actor 带入权限图。
        delegated_execution = kind is TraceEventKind.DELEGATION or delegated_ref is not None
        actor_id = (
            str(raw_actor)
            if delegated_execution and raw_actor is not None and raw_actor != raw_subject
            else subject_id
        )
        allowed = decision is TraceAuthorizationDecision.ALLOW or kind is TraceEventKind.DELEGATION
        events.append(
            TraceEvent(
                event_id=event_id,
                parent_event_ids=(parent_id,) if parent_id is not None else (),
                case_id=case_id,
                action_id=case.business_action,
                resource_ids=(case.resource,),
                kind=kind,
                semantic_key=str(record["semantic_key"]),
                subject_id=subject_id,
                actor_id=actor_id,
                credential_source=(
                    str(record["credential_source"])
                    if record.get("credential_source") is not None
                    else None
                ),
                authority_scope=TraceAuthorityScope(
                    allowed_action_ids=(case.business_action,) if allowed else (),
                    allowed_resource_ids=(case.resource,) if allowed else (),
                    origin_authorization_event_id=origin_ref,
                    delegated_from_event_id=delegated_ref,
                ),
                authorization_decision=decision,
                effect_id=(case.protected_effects[0] if record["semantic_key"] == effect_key else None),
                source_component=str(record.get("source_component") or "validation-fixture"),
                source_location=str(record.get("source_location") or "fixture:public-trace"),
                correlation_kind=TraceCorrelationKind.EXPLICIT_PARENT,
                evidence_refs=(evidence_ref,),
                recorded_at_us=int(record.get("recorded_at_us") or index),
            )
        )
        previous_id = event_id
    return ExecutionTrace(
        case_id=case_id,
        action_id=case.business_action,
        planned_subject_id=planned_subject_id,
        events=tuple(events),
        complete=complete,
        reason_codes=() if complete else ("VALIDATION_TRACE_INCOMPLETE",),
    )


def _known_reference(value: object, known_ids: set[str]) -> str | None:
    if value is None:
        return None
    reference = str(value)
    return reference if reference in known_ids else None


__all__ = ["ValidationDomainBundle", "build_validation_domain_bundle"]
