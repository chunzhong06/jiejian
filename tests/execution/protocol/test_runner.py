from __future__ import annotations

import hashlib
import json

import pytest

from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect, TargetType
from product.backend.core.verification.permission_coverage import build_permission_coverage_plan
from product.backend.core.verification.permissions import (
    ActionDefinition,
    CoverageDimension,
    PermissionContract,
    PermissionContext,
    PermissionExpectation,
    PermissionRule,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinition,
    SubjectDefinition,
)
from product.protocols import (
    ActionExecutionBinding,
    CausalityStatus,
    CleanupResult,
    CleanupStatus,
    Correlation,
    Evidence,
    ExecutionBudget,
    ExecutionFact,
    ExecutionProjectSnapshot,
    ObservationCompleteness,
    ObservationEnvelope,
    ObservationFact,
    ObservationPhase,
    ObservationProvenance,
    ObserverBudget,
    ObserverOutcome,
    ObserverOutcomeStatus,
    ObserverRequirementBinding,
    ObserverRequirementKind,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    OwnerApiLocator,
    ResourceInjection,
    RunnerInput,
    RunnerResult,
    RunnerResultType,
    SubjectExecutionBinding,
    TargetType,
    WebTargetDefinition,
    WebTargetScope,
    ExecutionIdentity,
    build_evidence,
    build_normalized_state,
    canonical_runner_json_bytes,
    canonical_runner_sha256,
    parse_runner_input,
)


def _contract_and_plan() -> tuple[PermissionContract, object]:
    contract = PermissionContract(
        contract_id="runner-contract",
        version=1,
        role_ids=("member",),
        workflow_states=("DRAFT",),
        subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant-a", department_id="dept-a"),),
        actions=(ActionDefinition(action_id="modify", side_effect=True),),
        resources=(ResourceDefinition(resource_id="document", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="member", workflow_state="DRAFT"),),
        relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),),
        rules=(PermissionRule(rule_id="modify-document", subject_id="member", action_id="modify", resource_id="document", relation_path=("owns-document",), context=PermissionContext(workflow_states=("DRAFT",), resource_ids=("document",)), expectation=PermissionExpectation.ALLOW, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.ROLE,)),),
    )
    plan = build_permission_coverage_plan(contract, engine_version="runner-test", seed=4, case_budget=1, available_observations=("resource_state",))
    return contract, plan


def _snapshot() -> ExecutionProjectSnapshot:
    contract, plan = _contract_and_plan()
    target = WebTargetDefinition(scope=WebTargetScope(base_url="http://127.0.0.1:8765", allowed_origins=("http://127.0.0.1:8765",), allowed_hosts=("127.0.0.1",), allowed_ports=(8765,), allow_private_network=True, timeout_seconds=5, max_requests=8, max_response_bytes=262_144), reset_path="/reset")
    identity = ExecutionIdentity(schema_version="2", id="identity-member", role="member", secret_ref="env:JIEJIAN_TEST_TOKEN")
    owner = ObserverSpec(observer_id="owner_observer", observer_type=ObserverType.OWNER_API, target=ObserverTarget(target_id="owner-target", locator=OwnerApiLocator(relative_path_template="/owner/resources/{resource_id}"), normalization_id="owner-state", normalization_version="1"), phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER), required=True, budget=ObserverBudget(timeout_us=5_000_000, max_rows=1, max_bytes=262_144))
    return ExecutionProjectSnapshot(
        project_id="runner-project",
        project_name="Runner test",
        target_type=TargetType.WEB,
        target=target,
        identities=(identity,),
        contract=contract,
        plan=plan,
        observers=(owner,),
        subject_bindings=(SubjectExecutionBinding(subject_id="member", identity_id="identity-member"),),
        action_bindings=(ActionExecutionBinding(action_id="modify", target_type=TargetType.WEB, method="PATCH", relative_path_template="/resources/{resource_id}", json_body={"value": "bounded"}, accepted_statuses=(200,), denied_statuses=(401, 403, 404), resource_injection=ResourceInjection.PATH_RESOURCE_ID),),
        observer_bindings=(ObserverRequirementBinding(requirement_id="resource_state", kind=ObserverRequirementKind.OBSERVER_SPEC, observer_id="owner_observer", observer_type=ObserverType.OWNER_API, credential_ref="env:OWNER_READ_ONLY", phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER)),),
        contract_fingerprint=__import__("product.backend.core.verification.permissions", fromlist=["canonical_sha256"]).canonical_sha256(contract),
        plan_fingerprint=plan.plan_fingerprint,
    )


def _input() -> RunnerInput:
    snapshot = _snapshot()
    return RunnerInput(run_id="run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", job_id="job_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", attempt=1, lease_owner="runner-test", fencing_token=2, created_at_us=100, budget=ExecutionBudget(max_requests=8, request_timeout_us=5_000_000, max_duration_us=20_000_000, max_response_bytes=262_144, max_cases=1, max_parallel_cases=1), project_snapshot=snapshot)


def _evidence(*, verdict: CaseVerdict = CaseVerdict.SAFE, available: bool = True, resource_ids=None) -> Evidence:
    snapshot = _snapshot()
    case = snapshot.plan.cases[0]
    resources = tuple(resource_ids or case.resource_ids)
    if resources != case.resource_ids:
        case = case.model_copy(update={"resource_ids": resources, "expectations": tuple(PermissionExpectation.ALLOW for _ in resources), "relation_paths": tuple(("owns-document",) for _ in resources), "batch_mode": None})
    states = tuple(build_normalized_state({"value": "old" if phase is ObservationPhase.BEFORE else "new"}) for phase in (ObservationPhase.BEFORE, ObservationPhase.AFTER))
    envelopes = tuple(ObservationEnvelope(observer_id="owner_observer", observer_type=ObserverType.OWNER_API, phase=phase, target_id="owner-target", window=__import__("product.protocols", fromlist=["ObservationWindow"]).ObservationWindow(phase=phase, started_at_us=1, finished_at_us=2, timeout_us=5_000_000), correlation=Correlation(case_id=case.case_id, resource_id=resource_id, request_marker=case.case_id), causality=CausalityStatus.CORRELATED, completeness=ObservationCompleteness.COMPLETE if available else ObservationCompleteness.MISSING, state=state if available else None, provenance=ObservationProvenance(provenance_type=__import__("product.protocols", fromlist=["ProvenanceType"]).ProvenanceType.OWNER_API, adapter_version="test", target_id="owner-target", source_sha256=state.canonical_sha256) if available else None, reason_codes=() if available else ("REQUIRED_OBSERVATION_INCOMPLETE",)) for resource_id in resources for phase, state in zip((ObservationPhase.BEFORE, ObservationPhase.AFTER), states, strict=True))
    outcomes = (ObserverOutcome(observer_id="owner_observer", required=True, status=ObserverOutcomeStatus.AVAILABLE if available else ObserverOutcomeStatus.INCONCLUSIVE, reason_codes=()),)
    observation_facts = tuple(ObservationFact(requirement_id="resource_state", resource_id=resource_id, effect=ObservedEffect.CONFIRMED if available else ObservedEffect.UNKNOWN, complete=available, reliable=available, reason_codes=() if available else ("REQUIRED_OBSERVATION_INCOMPLETE",)) for resource_id in resources)
    execution = ExecutionFact(case_id=case.case_id, action_id=case.action_id, target_type=TargetType.WEB, outcome=ExecutionOutcome.ACCEPTED, execution_marker=case.case_id, input_hash="a" * 64, output_hash="b" * 64)
    return build_evidence(schema_version="2", run_id="run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", case_snapshot=case, finding_pre_identity=case.finding_pre_identity, execution_fact=execution, requirement_bindings=tuple(snapshot.observer_bindings), observation_facts=observation_facts, observations=envelopes, outcomes=outcomes, verdict=verdict, reason_codes=())


def _rehash_evidence(raw: dict) -> dict:
    raw = dict(raw)
    raw.pop("evidence_id", None)
    raw.pop("evidence_hash", None)
    return build_evidence(**raw).model_dump(mode="python")


def test_current_runner_input_round_trips_with_web_target_and_execution_binding() -> None:
    document = _input()
    raw = canonical_runner_json_bytes(document)
    assert parse_runner_input(raw) == document
    assert document.project_snapshot.target_type is TargetType.WEB
    assert canonical_runner_sha256(document) == canonical_runner_sha256(parse_runner_input(raw))


def test_current_evidence_carries_execution_and_observation_facts() -> None:
    evidence = _evidence()
    assert evidence.execution_fact.outcome is ExecutionOutcome.ACCEPTED
    assert evidence.observation_facts[0].effect is ObservedEffect.CONFIRMED


def test_incomplete_observation_requires_inconclusive_verdict() -> None:
    evidence = _evidence(available=False, verdict=CaseVerdict.INCONCLUSIVE)
    assert evidence.verdict is CaseVerdict.INCONCLUSIVE


def test_evidence_rejects_missing_observation_fact_coverage() -> None:
    raw = _evidence().model_dump(mode="python")
    raw.pop("evidence_id")
    raw.pop("evidence_hash")
    raw["observation_facts"] = ()
    with pytest.raises(ValueError, match="exactly cover"):
        build_evidence(**raw)
