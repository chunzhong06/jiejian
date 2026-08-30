# 提供隔离 Runner 的请求构造与执行测试夹具。

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from product.backend.core.lifecycle import CaseVerdict, ProjectStatus
from product.backend.infra.storage import ProjectRecord
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect, TargetType, TemporalClosure, aggregate_security_effect
from product.backend.core.verification.permissions.coverage import build_permission_coverage_plan
from product.backend.core.verification.permissions import (
    ActionDefinition,
    BatchAuthorizationMode,
    CoverageDimension,
    PermissionContract,
    PermissionContext,
    PermissionExpectation,
    PermissionRule,
    RelationEndpoint,
    RelationFact,
    RelationType,
    ResourceDefinition,
    SecurityEffectDefinition,
    SecurityEffectKind,
    SubjectDefinition,
    canonical_json_bytes,
    permission_model_sha256,
)
from product.protocols import (
    BearerIdentityBinding,
    BaselineIntegrityMode,
    BaselineProjection,
    CausalityStatus,
    Correlation,
    Evidence,
    EffectBinding,
    EffectClosurePolicy,
    ExecutionBudget,
    ExecutionFact,
    WebExecutionIdentity,
    WebExecutionProfile,
    WebExecutionSnapshot,
    ObservationCompleteness,
    ObservationEnvelope,
    ObservationFact,
    ObservationPhase,
    ObservationProvenance,
    ObservationWindow,
    ObserverBudget,
    ObserverOutcome,
    ObserverOutcomeStatus,
    ObserverRequirementBinding,
    ObserverRequirementKind,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    OwnerApiLocator,
    ProvenanceType,
    HttpOutcomeClassifier,
    HttpPredicate,
    HttpPredicateKind,
    HttpRequestTemplate,
    HttpWorkflowBinding,
    HttpWorkflowStep,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
    WorkflowStepPurpose,
    RunnerInput,
    SubjectExecutionBinding,
    WebTargetDefinition,
    WebTargetScope,
    build_evidence,
    build_normalized_state,
    canonical_web_execution_profile_json_bytes,
    parse_web_execution_profile,
)
from product.protocols.web.workflow import CASE_SUBJECT_IDENTITY


def seed_project_from_generated_profile(app: Any, profile_path: Path) -> dict[str, object]:
    """为执行测试写入已由正式编译链生成的项目身份，不恢复生产注册入口。"""

    profile = parse_web_execution_profile(profile_path.read_bytes())
    now_us = time.time_ns() // 1_000
    record = ProjectRecord(
        project_id=profile.project_id,
        name=profile.project_name,
        status=ProjectStatus.READY,
        target_type=profile.target_type,
        governed_contract_id=None,
        governed_contract_version=None,
        created_at_us=now_us,
        updated_at_us=now_us,
    )
    with app.state.context.uow_factory() as work:
        work.projects.add(record)
        work.commit()
    return record.model_dump(mode="json")


def register_test_generated_profile(app: Any, profile_path: Path):
    """把测试输入放进正式 generated 边界，再走内部登记服务。"""

    profile = parse_web_execution_profile(profile_path.read_bytes())
    generated = (
        app.state.context.paths.data
        / "projects"
        / profile.project_id
        / "execution"
        / "generated"
    ).resolve()
    generated.mkdir(parents=True, exist_ok=True)
    generated_path = generated / f"{profile.profile_id}.json"
    generated_path.write_bytes(profile_path.read_bytes())

    def validate_generated(record: Any, current: WebExecutionProfile) -> None:
        Path(record.source_path).resolve().relative_to(generated)
        assert current.profile_id == profile.profile_id

    app.state.context.execution.set_generated_profile_validator(validate_generated)
    return app.state.context.execution.register_generated(generated_path)


def contract_and_plan() -> tuple[PermissionContract, object]:
    contract = PermissionContract(
        contract_id="runner-contract",
        version=1,
        role_ids=("member",),
        workflow_states=("DRAFT",),
        subjects=(SubjectDefinition(subject_id="member", roles=("member",), tenant_id="tenant-a", department_id="dept-a"),),
        effects=(SecurityEffectDefinition(effect_id="document-mutated", kind=SecurityEffectKind.STATE_MUTATION, resource_type="document"),),
        actions=(ActionDefinition(action_id="modify", effect_ids=("document-mutated",)),),
        resources=(ResourceDefinition(resource_id="document", resource_type="document", tenant_id="tenant-a", department_id="dept-a", owner_subject_id="member", workflow_state="DRAFT"),),
        relations=(RelationFact(relation_id="owns-document", relation=RelationType.OWNS, source=RelationEndpoint(endpoint_type="subject", endpoint_id="member"), target=RelationEndpoint(endpoint_type="resource", endpoint_id="document")),),
        rules=(PermissionRule(rule_id="modify-document", subject_id="member", action_id="modify", resource_id="document", relation_path=("owns-document",), context=PermissionContext(workflow_states=("DRAFT",), resource_ids=("document",)), expectation=PermissionExpectation.ALLOW, required_observations=("resource_state",), coverage_dimensions=(CoverageDimension.ROLE,)),),
    )
    plan = build_permission_coverage_plan(
        contract,
        engine_version="runner-test",
        seed=4,
        case_budget=1,
        available_observations=("resource_state",),
    )
    return contract, plan


def execution_snapshot() -> WebExecutionSnapshot:
    contract, plan = contract_and_plan()
    target = WebTargetDefinition(
        scope=WebTargetScope(
            base_url="http://127.0.0.1:8765",
            allowed_origins=("http://127.0.0.1:8765",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(8765,),
            allow_private_network=True,
            timeout_seconds=5,
            max_requests=8,
            max_response_bytes=262_144,
        ),
        reset_path="/reset",
    )
    identity = WebExecutionIdentity(
        identity_id="identity-member",
        role="member",
        binding=BearerIdentityBinding(secret_ref="env:JIEJIAN_TEST_TOKEN"),
    )
    owner = ObserverSpec(
        observer_id="owner_observer",
        observer_type=ObserverType.OWNER_API,
        target=ObserverTarget(
            target_id="owner-target",
            locator=OwnerApiLocator(relative_path_template="/owner/resources/{resource_id}"),
            normalization_id="owner-state",
            normalization_version="1",
        ),
        phases=(ObservationPhase.BASELINE, ObservationPhase.BEFORE, ObservationPhase.AFTER),
        required=True,
        budget=ObserverBudget(timeout_us=5_000_000, max_rows=1, max_bytes=262_144),
    )
    workflow = HttpWorkflowBinding(
        workflow_id="modify-workflow",
        source_flow_id="runner-flow",
        action_id="modify",
        steps=(HttpWorkflowStep(
            id="target-1",
            purpose=WorkflowStepPurpose.TARGET,
            identity_id="identity-member",
            request_template=HttpRequestTemplate(
                method="PATCH",
                path="/resources/{resource_id}",
                body={"kind": "JSON", "value": {"value": "bounded"}},
                input_slots=(ValueSlot(slot_id="resource_id", source=ValueSlotSource.CASE_RESOURCE_ID, consumer=ValueSlotConsumer.PATH, consumer_step_id="target-1"),),
            ),
            classifier=HttpOutcomeClassifier(
                accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(200,)),),
                denied=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(401, 403, 404)),),
            ),
        ),),
        target_step_id="target-1",
        baseline_projections=(BaselineProjection(
            projection_id="document-state",
            logical_resource_handle="case-resource",
            normalization_version="1",
            projection_version="1",
            integrity_mode=BaselineIntegrityMode.EXACT_RESTORE,
        ),),
    )
    observer_binding = ObserverRequirementBinding(requirement_id="resource_state", kind=ObserverRequirementKind.OBSERVER_SPEC, observer_id="owner_observer", observer_type=ObserverType.OWNER_API, credential_ref="env:OWNER_READ_ONLY", phases=(ObservationPhase.BASELINE, ObservationPhase.BEFORE, ObservationPhase.AFTER))
    profile = WebExecutionProfile(
        project_id="runner-project",
        profile_id="runner-profile",
        project_name="Runner test",
        target_type=TargetType.WEB,
        target=target,
        identities=(identity,),
        contract_id=contract.contract_id,
        contract_version=contract.version,
        observers=(owner,),
        subject_bindings=(SubjectExecutionBinding(subject_id="member", identity_id="identity-member"),),
        workflow_bindings=(workflow,),
        effect_bindings=(EffectBinding(effect_id="document-mutated", required_channels=("resource_state",), closure_policy=EffectClosurePolicy.IMMEDIATE, projection_version="v1"),),
        observer_bindings=(observer_binding,),
        seed=4,
        case_budget=1,
        max_relation_depth=8,
        max_duration_us=20_000_000,
    )
    return profile.build_snapshot(contract, plan)


def runner_input() -> RunnerInput:
    snapshot = execution_snapshot()
    return RunnerInput(
        run_id="run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        job_id="job_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        attempt=1,
        lease_owner="runner-test",
        fencing_token=2,
        created_at_us=100,
        budget=ExecutionBudget(
            max_requests=8,
            request_timeout_us=5_000_000,
            max_duration_us=20_000_000,
            max_response_bytes=262_144,
            max_cases=1,
            max_parallel_cases=1,
        ),
        project_snapshot=snapshot,
    )


def evidence(
    *,
    verdict: CaseVerdict = CaseVerdict.SAFE,
    available: bool = True,
    resource_ids=None,
) -> Evidence:
    snapshot = execution_snapshot()
    case = snapshot.plan.cases[0]
    resources = tuple(resource_ids or case.resource_ids)
    if resources != case.resource_ids:
        case = case.model_copy(
            update={
                "resource_ids": resources,
                "expectations": tuple(PermissionExpectation.ALLOW for _ in resources),
                "relation_paths": tuple(("owns-document",) for _ in resources),
                "batch_mode": (
                    BatchAuthorizationMode.ALL_ALLOW
                    if len(resources) > 1
                    else None
                ),
            }
        )
    phases = (ObservationPhase.BASELINE, ObservationPhase.BEFORE, ObservationPhase.AFTER)
    states = tuple(
        build_normalized_state({"value": "new" if phase is ObservationPhase.AFTER else "old"})
        for phase in phases
    )
    envelopes = tuple(
        ObservationEnvelope(
            observer_id="owner_observer",
            observer_type=ObserverType.OWNER_API,
            phase=phase,
            target_id="owner-target",
            window=ObservationWindow(
                phase=phase,
                started_at_us=1,
                finished_at_us=2,
                timeout_us=5_000_000,
            ),
            correlation=Correlation(
                case_id=case.case_id,
                resource_id=resource_id,
                request_marker=case.case_id,
            ),
            causality=CausalityStatus.CORRELATED,
            completeness=(
                ObservationCompleteness.COMPLETE
                if available
                else ObservationCompleteness.MISSING
            ),
            state=state if available else None,
            provenance=(
                ObservationProvenance(
                    provenance_type=ProvenanceType.OWNER_API,
                    adapter_version="test",
                    target_id="owner-target",
                    source_sha256=state.canonical_sha256,
                )
                if available
                else None
            ),
            reason_codes=() if available else ("REQUIRED_OBSERVATION_INCOMPLETE",),
        )
        for resource_id in resources
        for phase, state in zip(phases, states, strict=True)
    )
    outcomes = (
        ObserverOutcome(
            observer_id="owner_observer",
            required=True,
            status=(
                ObserverOutcomeStatus.AVAILABLE
                if available
                else ObserverOutcomeStatus.INCONCLUSIVE
            ),
            reason_codes=(),
        ),
    )
    observation_facts = tuple(
        ObservationFact(
            effect_id=snapshot.contract.effects[0].effect_id,
            requirement_id="resource_state",
            resource_id=resource_id,
            effect=ObservedEffect.CONFIRMED if available else ObservedEffect.UNKNOWN,
            complete=available,
            reliable=available,
            correlated=available,
            temporal_closure=TemporalClosure.CLOSED if available else TemporalClosure.UNKNOWN,
            reason_codes=() if available else ("REQUIRED_OBSERVATION_INCOMPLETE",),
        )
        for resource_id in resources
    )
    execution = ExecutionFact(
        case_id=case.case_id,
        action_id=case.action_id,
        target_type=TargetType.WEB,
        outcome=ExecutionOutcome.ACCEPTED,
        execution_marker=case.case_id,
        input_hash="a" * 64,
        output_hash="b" * 64,
    )
    effect_facts = tuple(
        aggregate_security_effect(
            snapshot.contract.effects[0],
            resource_id=resource_id,
            required_requirement_ids=("resource_state",),
            corroborating_requirement_ids=(),
            observations=observation_facts,
            baseline_integrity=available,
        )
        for resource_id in resources
    )
    return build_evidence(
        schema_version="1",
        run_id="run_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        case_snapshot=case,
        twin_snapshot=None,
        twin_role=None,
        allow_control_valid=available,
        baseline_integrity=available,
        finding_pre_identity=case.finding_pre_identity,
        execution_fact=execution,
        requirement_bindings=tuple(snapshot.observer_bindings),
        observation_facts=observation_facts,
        security_effect_facts=effect_facts,
        observations=envelopes,
        outcomes=outcomes,
        verdict=verdict,
        reason_codes=(),
    )


def rehash_evidence(raw: dict) -> dict:
    raw = dict(raw)
    raw.pop("evidence_id", None)
    raw.pop("evidence_hash", None)
    return build_evidence(**raw).model_dump(mode="python")


def write_web_test_profile(
    directory: Path,
    *,
    port: int = 8765,
    project_id: str = "web-test-project",
    profile_id: str = "web-test-profile",
    project_name: str = "Web 测试项目",
    include_comparison_subject: bool = False,
) -> tuple[Path, Path]:
    """在用例临时目录生成中性 Web Profile 与权限 Contract。"""

    contract, _ = contract_and_plan()
    contract = contract.model_copy(update={"contract_id": "web-test-contract"})
    if include_comparison_subject:
        contract = contract.model_copy(
            update={
                "role_ids": ("member", "reader"),
                "subjects": contract.subjects
                + (
                    SubjectDefinition(
                        subject_id="guest",
                        roles=("reader",),
                        tenant_id="tenant-a",
                        department_id="dept-a",
                    ),
                ),
            }
        )
    scope = WebTargetScope(
        base_url=f"http://127.0.0.1:{port}",
        allowed_origins=(f"http://127.0.0.1:{port}",),
        allowed_hosts=("127.0.0.1",),
        allowed_ports=(port,),
        allow_private_network=True,
        timeout_seconds=5,
        max_requests=64,
        max_response_bytes=262_144,
    )
    target = WebTargetDefinition(scope=scope, reset_path="/reset")
    identity = WebExecutionIdentity(
        identity_id="test-member",
        role="member",
        binding=BearerIdentityBinding(secret_ref="env:JIEJIAN_WEB_TEST_MEMBER_TOKEN"),
    )
    identities = [identity]
    subject_bindings = [
        SubjectExecutionBinding(subject_id="member", identity_id=identity.identity_id)
    ]
    if include_comparison_subject:
        identities.append(
            WebExecutionIdentity(
                identity_id="test-reader",
                role="reader",
                binding=BearerIdentityBinding(
                    secret_ref="env:JIEJIAN_WEB_TEST_READER_TOKEN"
                ),
            )
        )
        subject_bindings.append(
            SubjectExecutionBinding(subject_id="guest", identity_id="test-reader")
        )
    observer = ObserverSpec(
        observer_id="state-observer",
        observer_type=ObserverType.OWNER_API,
        target=ObserverTarget(
            target_id="state-target",
            locator=OwnerApiLocator(relative_path_template="/observations/{resource_id}"),
            normalization_id="resource-state",
            normalization_version="1",
        ),
        phases=(ObservationPhase.BASELINE, ObservationPhase.BEFORE, ObservationPhase.AFTER),
        required=True,
        budget=ObserverBudget(timeout_us=5_000_000, max_rows=1, max_bytes=262_144),
    )
    step = HttpWorkflowStep(
        id="target-step",
        purpose=WorkflowStepPurpose.TARGET,
        identity_id=CASE_SUBJECT_IDENTITY,
        request_template=HttpRequestTemplate(
            method="PATCH",
            path="/resources/{resource_id}",
            body={"kind": "JSON", "value": {"value": "bounded"}},
            input_slots=(ValueSlot(
                slot_id="resource_id",
                source=ValueSlotSource.CASE_RESOURCE_ID,
                consumer=ValueSlotConsumer.PATH,
                consumer_step_id="target-step",
            ),),
        ),
        classifier=HttpOutcomeClassifier(
            accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(200,)),),
            denied=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(401, 403, 404)),),
        ),
    )
    workflow = HttpWorkflowBinding(
        workflow_id="modify-workflow",
        source_flow_id="web-test-flow",
        action_id="modify",
        steps=(step,),
        target_step_id=step.id,
        baseline_projections=(BaselineProjection(
            projection_id="resource-state",
            logical_resource_handle="case-resource",
            normalization_version="1",
            projection_version="1",
            integrity_mode=BaselineIntegrityMode.EXACT_RESTORE,
        ),),
    )
    binding = ObserverRequirementBinding(
        requirement_id="resource_state",
        kind=ObserverRequirementKind.OBSERVER_SPEC,
        observer_id="state-observer",
        observer_type=ObserverType.OWNER_API,
        credential_ref="env:JIEJIAN_WEB_TEST_OBSERVER_TOKEN",
        phases=(ObservationPhase.BASELINE, ObservationPhase.BEFORE, ObservationPhase.AFTER),
    )
    case_budget = 2 if include_comparison_subject else 1
    profile = WebExecutionProfile(
        profile_id=profile_id,
        project_id=project_id,
        project_name=project_name,
        target=target,
        identities=tuple(identities),
        contract_id=contract.contract_id,
        contract_version=contract.version,
        observers=(observer,),
        subject_bindings=tuple(subject_bindings),
        workflow_bindings=(workflow,),
        effect_bindings=(EffectBinding(
            effect_id="document-mutated",
            required_channels=("resource_state",),
            closure_policy=EffectClosurePolicy.IMMEDIATE,
            projection_version="v1",
        ),),
        observer_bindings=(binding,),
        seed=4,
        case_budget=case_budget,
        max_relation_depth=8,
        max_duration_us=20_000_000,
    )
    directory.mkdir(parents=True, exist_ok=True)
    profile_path = directory / "profile.json"
    contract_path = directory / "contract.json"
    profile_path.write_bytes(canonical_web_execution_profile_json_bytes(profile))
    contract_path.write_bytes(canonical_json_bytes(contract))
    return profile_path, contract_path
