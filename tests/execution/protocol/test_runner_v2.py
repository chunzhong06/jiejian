from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from jiejian.protocols import runner_v2 as runner_v2_module

from jiejian.domain.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from jiejian.protocols import (
    ActionExecutionBindingV2,
    CausalityStatus,
    CleanupResultV2,
    CleanupStatusV2,
    CorrelationV2,
    EvidenceV2,
    ExecutionBudgetV2,
    ExecutionProjectSnapshotV2,
    NormalizedStateV2,
    ObservationCompleteness,
    ObservationEnvelopeV2,
    ObservationPhase,
    ObservationProvenanceV2,
    ObservationWindowV2,
    ObserverBudgetV2,
    ObserverRequirementBindingV2,
    ObserverRequirementKindV2,
    ObserverSpecV2,
    ObserverOutcomeV2,
    ObserverOutcomeStatus,
    ObserverTargetV2,
    ObserverType,
    OwnerApiLocatorV2,
    ProvenanceType,
    RequestFactV2,
    ResourceInjectionV2,
    RunnerErrorV2,
    RunnerInputV2,
    RunnerResultTypeV2,
    RunnerResultV2,
    SubjectExecutionBindingV2,
    canonical_runner_v2_json_bytes,
    canonical_runner_v2_sha256,
    build_evidence_v2,
    build_normalized_state,
    parse_runner_input_v2,
)
from jiejian.verification.permission_coverage import build_permission_coverage_plan
from jiejian.verification.permissions import (
    ActionDefinition,
    BatchAuthorizationMode,
    PermissionContractV2,
    PermissionContext,
    PermissionExpectation,
    PermissionRuleV2,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinitionV2,
    SubjectDefinition,
    CoverageDimension,
    canonical_sha256,
)
from jiejian.verification.models import Flow, FlowStep, Identity, TargetScope


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _contract_and_plan():
    contract = PermissionContractV2(
        contract_id="runner-contract",
        version=1,
        role_ids=("member",),
        workflow_states=("DRAFT",),
        subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant-a", department_id="dept-a"),),
        actions=(ActionDefinition(action_id="modify", flow_step_ids=("modify-step",), side_effect=True),),
        resources=(ResourceDefinitionV2(resource_id="document", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="member", workflow_state="DRAFT"),),
        relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),),
        rules=(PermissionRuleV2(rule_id="modify-document", subject_id="member", action_id="modify", resource_id="document", relation_path=("owns-document",), context=PermissionContext(workflow_states=("DRAFT",), resource_ids=("document",)), expectation=PermissionExpectation.ALLOW, required_observers=("http", "owner_api"), coverage_dimensions=(CoverageDimension.ROLE,)),),
    )
    plan = build_permission_coverage_plan(contract, engine_version="runner-v2-test", seed=4, case_budget=1, available_observers=("http", "owner_api"))
    return contract, plan


def _snapshot() -> ExecutionProjectSnapshotV2:
    contract, plan = _contract_and_plan()
    target = TargetScope(
        schema_version="1",
        base_url="http://127.0.0.1:8765",
        allowed_origins=("http://127.0.0.1:8765",),
        allowed_hosts=("127.0.0.1",),
        allowed_ports=(8765,),
        allow_private_network=True,
        timeout_seconds=5,
        max_requests=8,
        max_response_bytes=262_144,
    )
    identity = Identity(schema_version="1", id="identity-member", role="member", secret_ref="env:JIEJIAN_TEST_TOKEN")
    flow = Flow(
        schema_version="1",
        id="runner-flow",
        steps=(
            FlowStep(
                schema_version="1",
                id="modify-step",
                method="PATCH",
                path="/resources/{resource_id}",
                identity_id="identity-member",
                resource_id="document",
                alternate_identity_id="identity-member",
                alternate_resource_id="document",
                json_body={"value": "bounded"},
            ),
        ),
    )
    owner = ObserverSpecV2(
        observer_id="owner_observer",
        observer_type=ObserverType.OWNER_API,
        target=ObserverTargetV2(target_id="owner-target", locator=OwnerApiLocatorV2(relative_path_template="/owner/resources/{resource_id}"), normalization_id="owner-state", normalization_version="1"),
        phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER),
        required=True,
        budget=ObserverBudgetV2(timeout_us=5_000_000, max_rows=1, max_bytes=262_144),
    )
    return ExecutionProjectSnapshotV2(
        project_id="runner-project",
        project_name="Runner V2 test",
        target=target,
        identities=(identity,),
        flow=flow,
        contract=contract,
        plan=plan,
        observers=(owner,),
        subject_bindings=(SubjectExecutionBindingV2(subject_id="member", identity_id="identity-member"),),
        action_bindings=(ActionExecutionBindingV2(action_id="modify", flow_step_id="modify-step", resource_injection=ResourceInjectionV2.PATH_RESOURCE_ID),),
        observer_bindings=(
            ObserverRequirementBindingV2(requirement_id="http", kind=ObserverRequirementKindV2.REQUEST_FACT),
            ObserverRequirementBindingV2(requirement_id="owner_api", kind=ObserverRequirementKindV2.OBSERVER_SPEC, observer_id="owner_observer", observer_type=ObserverType.OWNER_API, owner_api_credential_ref="env:OWNER_READ_ONLY", phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER)),
        ),
        contract_fingerprint=canonical_sha256(contract),
        plan_fingerprint=plan.plan_fingerprint,
    )


def _input() -> RunnerInputV2:
    snapshot = _snapshot()
    return RunnerInputV2(
        run_id="run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        job_id="job_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        attempt=1,
        lease_owner="runner-v2-test",
        fencing_token=2,
        created_at_us=100,
        budget=ExecutionBudgetV2(max_requests=8, request_timeout_us=5_000_000, max_duration_us=20_000_000, max_response_bytes=262_144, max_cases=1, max_parallel_cases=1),
        project_snapshot=snapshot,
    )


def _evidence(*, verdict: CaseVerdict = CaseVerdict.SAFE, available: bool = True, phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER), binding_phases=None, resource_ids=None) -> EvidenceV2:
    snapshot = _snapshot()
    case = snapshot.plan.cases[0]
    if resource_ids is not None:
        case = case.model_copy(update={
            "resource_ids": tuple(resource_ids),
            "expectations": tuple(PermissionExpectation.ALLOW for _ in resource_ids),
            "relation_paths": tuple(("owns-document",) for _ in resource_ids),
            "batch_mode": BatchAuthorizationMode.ALL_ALLOW,
            "atomic": True,
        })
    state = build_normalized_state({"status_code": 200})
    envelopes = tuple(
        ObservationEnvelopeV2(
            observer_id="owner_observer",
            observer_type=ObserverType.OWNER_API,
            phase=phase,
            target_id="owner-target",
            window=ObservationWindowV2(phase=phase, started_at_us=1, finished_at_us=2, timeout_us=5_000_000),
            correlation=CorrelationV2(case_id=case.case_id, resource_id=resource_id or case.resource_ids[0], request_marker="case-marker"),
            causality=CausalityStatus.CORRELATED,
            completeness=ObservationCompleteness.COMPLETE if available else ObservationCompleteness.MISSING,
            state=state if available else None,
            provenance=ObservationProvenanceV2(provenance_type=ProvenanceType.OWNER_API, adapter_version="owner-1", target_id="owner-target", source_sha256="a" * 64) if available else None,
            reason_codes=() if available else ("OWNER_API_MISSING",),
        )
        for resource_id in (resource_ids or (case.resource_ids[0],))
        for phase in phases
    )
    outcome = ObserverOutcomeV2(observer_id="owner_observer", required=True, status=ObserverOutcomeStatus.AVAILABLE if available else ObserverOutcomeStatus.INCONCLUSIVE, reason_codes=() if available else ("OWNER_API_MISSING",))
    request = RequestFactV2(method="PATCH", relative_path="/resources/document", status_code=403, request_marker="case-marker", failure_code=None, request_sha256="b" * 64, response_sha256="c" * 64, request_byte_count=20, response_byte_count=12)
    bindings = (
        ObserverRequirementBindingV2(requirement_id="http", kind=ObserverRequirementKindV2.REQUEST_FACT),
        ObserverRequirementBindingV2(requirement_id="owner_api", kind=ObserverRequirementKindV2.OBSERVER_SPEC, observer_id="owner_observer", observer_type=ObserverType.OWNER_API, owner_api_credential_ref="env:OWNER_READ_ONLY", phases=phases if binding_phases is None else binding_phases),
    )
    raw = {
        "schema_version": "2",
        "evidence_id": "ev_00000000000000000000",
        "run_id": "run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "case_snapshot": case,
        "finding_pre_identity": case.finding_pre_identity,
        "request_fact": request,
        "requirement_bindings": bindings,
        "observations": envelopes,
        "outcomes": (outcome,),
        "verdict": verdict,
        "reason_codes": () if available else ("OWNER_API_MISSING",),
    }
    payload = {**raw, "evidence_hash": "0" * 64}
    payload.pop("evidence_hash")
    payload.pop("evidence_id")
    semantic_payload = _jsonable_for_test(payload)
    semantic_payload["observations"] = sorted(semantic_payload["observations"], key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]))
    payload["evidence_hash"] = runner_v2_module._sha256_json(semantic_payload)
    payload["evidence_id"] = f"ev_{payload['evidence_hash'][:20]}"
    return EvidenceV2(**payload)


def _jsonable_for_test(value):
    if hasattr(value, "model_dump"):
        return _jsonable_for_test(value.model_dump(mode="python"))
    if hasattr(value, "value") and not isinstance(value, (dict, list, tuple, str, int, bool)):
        return value.value
    if isinstance(value, dict):
        return {str(k): _jsonable_for_test(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable_for_test(v) for v in value]
    return value


def _rehash_evidence(raw):
    payload = _jsonable_for_test(raw)
    payload.pop("evidence_id", None)
    payload.pop("evidence_hash", None)
    payload["observations"] = sorted(payload["observations"], key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]))
    raw["evidence_hash"] = runner_v2_module._sha256_json(payload)
    raw["evidence_id"] = f"ev_{raw['evidence_hash'][:20]}"
    return raw


def test_input_round_trip_and_canonical_order_are_stable() -> None:
    document = _input()
    raw = canonical_runner_v2_json_bytes(document)
    assert parse_runner_input_v2(raw) == document
    assert canonical_runner_v2_sha256(document) == canonical_runner_v2_sha256(parse_runner_input_v2(raw))
    assert b"opaque-token-value" not in raw


def test_snapshot_rejects_unbound_requirement_and_bad_fingerprint() -> None:
    snapshot = _snapshot().model_dump(mode="python")
    snapshot["observer_bindings"] = (snapshot["observer_bindings"][0],)
    with pytest.raises(ValidationError):
        ExecutionProjectSnapshotV2.model_validate(snapshot)


def test_snapshot_rejects_shared_observer_id_across_requirements() -> None:
    snapshot = _snapshot().model_dump(mode="python")
    duplicate = ObserverRequirementBindingV2(
        requirement_id="owner_api_copy",
        kind=ObserverRequirementKindV2.OBSERVER_SPEC,
        observer_id="owner_observer",
        observer_type=ObserverType.OWNER_API,
        owner_api_credential_ref="env:OWNER_READ_ONLY",
        phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER),
    )
    snapshot["observer_bindings"] = (*snapshot["observer_bindings"], duplicate)
    with pytest.raises(ValidationError):
        ExecutionProjectSnapshotV2.model_validate(snapshot)


def test_observer_binding_requires_owner_credential_and_case_phases() -> None:
    with pytest.raises(ValidationError):
        ObserverRequirementBindingV2(
            requirement_id="owner_api",
            kind=ObserverRequirementKindV2.OBSERVER_SPEC,
            observer_id="owner-observer",
            observer_type=ObserverType.OWNER_API,
            phases=(ObservationPhase.BEFORE,),
        )
    binding = ObserverRequirementBindingV2(
        requirement_id="owner_api",
        kind=ObserverRequirementKindV2.OBSERVER_SPEC,
        observer_id="owner-observer",
        observer_type=ObserverType.OWNER_API,
        owner_api_credential_ref="env:OWNER_READ_ONLY",
        phases=(ObservationPhase.BEFORE, ObservationPhase.EVENTUAL),
    )
    assert binding.owner_api_credential_ref == "env:OWNER_READ_ONLY"
    with pytest.raises(ValidationError):
        ObserverRequirementBindingV2(
            requirement_id="sqlite",
            kind=ObserverRequirementKindV2.OBSERVER_SPEC,
            observer_id="sqlite-observer",
            observer_type=ObserverType.READ_ONLY_SQLITE,
            owner_api_credential_ref="env:OWNER_READ_ONLY",
            phases=(ObservationPhase.BEFORE,),
        )
    with pytest.raises(ValidationError):
        ObserverRequirementBindingV2(
            requirement_id="owner_api",
            kind=ObserverRequirementKindV2.OBSERVER_SPEC,
            observer_id="owner-observer",
            observer_type=ObserverType.OWNER_API,
            owner_api_credential_ref="env:OWNER_READ_ONLY",
            phases=(ObservationPhase.INITIAL,),
        )
    with pytest.raises(ValidationError):
        ObserverRequirementBindingV2(
            requirement_id="owner_api",
            kind=ObserverRequirementKindV2.OBSERVER_SPEC,
            observer_id="owner-observer",
            observer_type=ObserverType.OWNER_API,
            owner_api_credential_ref="env:OWNER_READ_ONLY",
            phases=(ObservationPhase.BASELINE,),
        )
    with pytest.raises(ValidationError):
        ObserverRequirementBindingV2(
            requirement_id="http",
            kind=ObserverRequirementKindV2.REQUEST_FACT,
            owner_api_credential_ref="env:OWNER_READ_ONLY",
        )
    with pytest.raises(ValidationError):
        ObserverRequirementBindingV2(
            requirement_id="owner_api",
            kind=ObserverRequirementKindV2.OBSERVER_SPEC,
            observer_id="owner-observer",
            observer_type=ObserverType.OWNER_API,
            owner_api_credential_ref="literal-owner-token",
            phases=(ObservationPhase.BEFORE,),
        )


def test_runner_v2_credential_ref_is_only_a_nonsecret_reference() -> None:
    raw = canonical_runner_v2_json_bytes(_input())
    assert b"env:OWNER_READ_ONLY" in raw
    assert b"literal-owner-token" not in raw
    assert b"opaque-token-value" not in raw
    snapshot = _snapshot().model_dump(mode="python")
    binding = {**snapshot["observer_bindings"][1], "observer_type": ObserverType.READ_ONLY_SQLITE}
    snapshot["observer_bindings"] = (snapshot["observer_bindings"][0], binding)
    with pytest.raises(ValidationError):
        ExecutionProjectSnapshotV2.model_validate(snapshot)
    snapshot = _snapshot().model_dump(mode="python")
    snapshot["contract_fingerprint"] = "0" * 64
    with pytest.raises(ValidationError):
        ExecutionProjectSnapshotV2.model_validate(snapshot)


def test_evidence_requires_correlated_complete_observer() -> None:
    evidence = _evidence()
    assert evidence.verdict is CaseVerdict.SAFE
    incomplete = _evidence(available=False, verdict=CaseVerdict.INCONCLUSIVE)
    assert incomplete.verdict is CaseVerdict.INCONCLUSIVE
    with pytest.raises(ValidationError):
        _evidence(available=False, verdict=CaseVerdict.SAFE)


def test_evidence_requires_every_declared_phase_for_safe_verdict() -> None:
    with pytest.raises(ValidationError):
        _evidence(phases=(ObservationPhase.BEFORE,), binding_phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER))
    assert _evidence(phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER)).verdict is CaseVerdict.SAFE


def test_batch_evidence_requires_each_resource_and_phase() -> None:
    evidence = _evidence(resource_ids=("document", "document-2"))
    assert len(evidence.observations) == 4
    assert evidence.verdict is CaseVerdict.SAFE
    with pytest.raises(ValidationError):
        _evidence(resource_ids=("document", "document-2"), phases=(ObservationPhase.BEFORE,), binding_phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER))
    with pytest.raises(ValidationError):
        EvidenceV2(**{
            **evidence.model_dump(mode="python"),
            "observations": evidence.observations[:-1],
        })


def test_batch_observation_keys_include_resource_and_allow_same_phase() -> None:
    evidence = _evidence(resource_ids=("document", "document-2"))
    keys = {(item.observer_id, item.phase, item.correlation.resource_id) for item in evidence.observations}
    assert len(keys) == 4
    duplicate = (*evidence.observations, evidence.observations[0])
    with pytest.raises(ValidationError):
        EvidenceV2(**{**evidence.model_dump(mode="python"), "observations": duplicate})


def test_inconclusive_batch_may_have_missing_resource_but_not_extra_resource() -> None:
    evidence = _evidence(resource_ids=("document", "document-2"), available=False, verdict=CaseVerdict.INCONCLUSIVE)
    partial = EvidenceV2(**_rehash_evidence({
        **evidence.model_dump(mode="python"),
        "observations": evidence.observations[:-1],
    }))
    assert partial.verdict is CaseVerdict.INCONCLUSIVE
    extra = evidence.observations[0].model_copy(update={
        "correlation": evidence.observations[0].correlation.model_copy(update={"resource_id": "document-3"}),
    })
    with pytest.raises(ValidationError):
        EvidenceV2(**{**evidence.model_dump(mode="python"), "observations": (*evidence.observations, extra)})


def test_evidence_rejects_unbound_observation() -> None:
    raw = _evidence().model_dump(mode="python")
    extra = {**raw["observations"][0], "observer_id": "unknown-observer"}
    raw["observations"] = (*raw["observations"], extra)
    with pytest.raises(ValidationError):
        EvidenceV2(**raw)


def test_evidence_without_response_can_only_be_inconclusive() -> None:
    evidence = _evidence(verdict=CaseVerdict.INCONCLUSIVE)
    raw = evidence.model_dump(mode="python")
    raw["request_fact"] = RequestFactV2(
        method="PATCH",
        relative_path="/resources/document",
        status_code=None,
        failure_code="REQUEST_TIMEOUT",
        request_marker="case-marker",
        request_sha256="b" * 64,
        response_sha256="c" * 64,
        request_byte_count=20,
        response_byte_count=0,
    )
    payload = {**raw, "evidence_hash": "0" * 64}
    payload.pop("evidence_hash")
    payload.pop("evidence_id")
    semantic_payload = _jsonable_for_test(payload)
    semantic_payload["observations"] = sorted(semantic_payload["observations"], key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]))
    payload["evidence_hash"] = runner_v2_module._sha256_json(semantic_payload)
    payload["evidence_id"] = f"ev_{payload['evidence_hash'][:20]}"
    assert EvidenceV2(**payload).verdict is CaseVerdict.INCONCLUSIVE
    payload["verdict"] = CaseVerdict.SAFE
    semantic_payload = _jsonable_for_test(payload)
    semantic_payload["observations"] = sorted(semantic_payload["observations"], key=lambda item: (item["observer_id"], item["phase"], item["correlation"]["resource_id"]))
    payload["evidence_hash"] = runner_v2_module._sha256_json(semantic_payload)
    payload["evidence_id"] = f"ev_{payload['evidence_hash'][:20]}"
    with pytest.raises(ValidationError):
        EvidenceV2(**payload)


def test_evidence_identity_is_content_addressed() -> None:
    first = _evidence()
    second = _evidence()
    assert first.evidence_hash == second.evidence_hash
    assert first.evidence_id == second.evidence_id == f"ev_{first.evidence_hash[:20]}"
    with pytest.raises(ValidationError):
        EvidenceV2(**{**first.model_dump(mode="python"), "evidence_id": "arbitrary-evidence-id"})


def test_batch_json_binding_allows_validated_business_fields() -> None:
    snapshot = _snapshot()
    extra_resource = ResourceDefinitionV2(resource_id="document-2", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="member", workflow_state="DRAFT")
    contract = snapshot.contract.model_copy(update={
        "actions": (snapshot.contract.actions[0].model_copy(update={"is_batch": True}),),
        "resources": (*snapshot.contract.resources, extra_resource),
    })
    batch_case = snapshot.plan.cases[0].model_copy(update={
        "resource_ids": ("document", "document-2"),
        "expectations": (PermissionExpectation.ALLOW, PermissionExpectation.ALLOW),
        "relation_paths": (("owns-document",), ("owns-document",)),
        "batch_mode": BatchAuthorizationMode.ALL_ALLOW,
        "atomic": True,
    })
    plan = snapshot.plan.model_copy(update={
        "cases": (batch_case,),
        "contract_fingerprint": canonical_sha256(contract),
    })
    flow_step = snapshot.flow.steps[0].model_copy(update={
        "path": "/resources/batch",
        "json_body": {"resource_ids": "{resource_ids}", "value": "bounded"},
    })
    data = snapshot.model_dump(mode="python")
    data.update({
        "contract": contract,
        "plan": plan,
        "flow": snapshot.flow.model_copy(update={"steps": (flow_step,)}),
        "action_bindings": (snapshot.action_bindings[0].model_copy(update={"resource_injection": ResourceInjectionV2.JSON_RESOURCE_IDS}),),
        "contract_fingerprint": canonical_sha256(contract),
    })
    assert ExecutionProjectSnapshotV2(**data).action_bindings[0].resource_injection is ResourceInjectionV2.JSON_RESOURCE_IDS
    data["flow"] = snapshot.flow.model_copy(update={"steps": (flow_step.model_copy(update={"json_body": {"value": "bounded"}}),)})
    with pytest.raises(ValidationError):
        ExecutionProjectSnapshotV2(**data)


def test_result_aggregates_vulnerable_then_inconclusive() -> None:
    evidence = _evidence(verdict=CaseVerdict.VULNERABLE)
    result = RunnerResultV2(
        run_id="run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        job_id="job_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        attempt=1,
        lease_owner="runner-v2-test",
        fencing_token=2,
        finished_at_us=200,
        result_type=RunnerResultTypeV2.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=RunVerdict.BLOCK,
        cleanup=CleanupResultV2(status=CleanupStatusV2.SUCCEEDED),
        error=None,
        plan_fingerprint=_snapshot().plan.plan_fingerprint,
        coverage_record_count=1,
        coverage_gap_count=0,
        evidence=(evidence,),
    )
    assert result.verdict is RunVerdict.BLOCK
    with pytest.raises(ValidationError):
        RunnerResultV2(**{**result.model_dump(mode="python"), "verdict": RunVerdict.PASS})


def test_evidence_factory_computes_content_addressed_identity() -> None:
    evidence = _evidence()
    fields = evidence.model_dump(mode="python")
    fields.pop("evidence_id")
    fields.pop("evidence_hash")
    assert build_evidence_v2(**fields) == evidence
    with pytest.raises(TypeError):
        build_evidence_v2(**evidence.model_dump(mode="python"))


def test_result_coverage_gap_forces_inconclusive_and_duplicate_case_is_rejected() -> None:
    evidence = _evidence(verdict=CaseVerdict.INCONCLUSIVE)
    result = RunnerResultV2(
        run_id="run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        job_id="job_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        attempt=1,
        lease_owner="runner-v2-test",
        fencing_token=2,
        finished_at_us=200,
        result_type=RunnerResultTypeV2.SUCCESS,
        run_lifecycle=RunLifecycle.COMPLETED,
        job_state=JobState.SUCCEEDED,
        verdict=RunVerdict.INCONCLUSIVE,
        reason_codes=(),
        cleanup=CleanupResultV2(status=CleanupStatusV2.SUCCEEDED),
        error=None,
        plan_fingerprint=_snapshot().plan.plan_fingerprint,
        coverage_record_count=1,
        coverage_gap_count=1,
        evidence=(evidence,),
        artifacts=(),
    )
    assert result.verdict is RunVerdict.INCONCLUSIVE
    with pytest.raises(ValidationError):
        RunnerResultV2(**{**result.model_dump(mode="python"), "evidence": (evidence, evidence)})

    zero_case_gap = result.model_dump(mode="python")
    zero_case_gap["evidence"] = ()
    zero_case_gap["verdict"] = RunVerdict.INCONCLUSIVE
    assert RunnerResultV2(**zero_case_gap).evidence == ()


@pytest.mark.parametrize("raw", [b'\xef\xbb\xbf{}', b'{"schema_version":"2","schema_version":"2"}', b'{"x":NaN}'])
def test_v2_parser_rejects_bom_duplicate_and_nonfinite(raw: bytes) -> None:
    with pytest.raises(Exception):
        parse_runner_input_v2(raw)


@pytest.mark.parametrize(
    ("model", "schema_path"),
    [
        (RunnerInputV2, PROJECT_ROOT / "schemas" / "runner" / "runner-input-v2.schema.json"),
        (RunnerResultV2, PROJECT_ROOT / "schemas" / "runner" / "runner-result-v2.schema.json"),
        (EvidenceV2, PROJECT_ROOT / "schemas" / "runner" / "evidence-v2.schema.json"),
    ],
)
def test_checked_in_v2_schema_has_no_drift(model, schema_path: Path) -> None:
    assert schema_path.exists()
    assert json.loads(schema_path.read_text(encoding="utf-8")) == model.model_json_schema()
