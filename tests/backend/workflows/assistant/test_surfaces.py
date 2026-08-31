# 验证九类 AI surface 只引用正式短事实与现有实体。

from __future__ import annotations

from types import SimpleNamespace

from product.backend.core.application_understanding import (
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
)
from product.backend.core.lifecycle import ProjectStatus, RunLifecycle, RunVerdict
from product.backend.core.permission_intent import PermissionIntentRelation
from product.backend.core.recording import RecordingState
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.workflows.assistant import (
    AssistantTemplateId,
    ErrorDiagnosisContext,
    build_guidance_snapshot,
    diagnose_error,
)
from product.backend.workflows.assistant.surfaces import AssistantSurfaceResolver
from product.backend.workflows.permission_intents import PermissionIntentCellStatus
from product.backend.workflows.projects.readiness import (
    ActionPermissionReadinessView,
    ProjectReadinessView,
)
from product.backend.workflows.results.presentation import PresentedCaseVerdict
from product.backend.workflows.security_setup.checks import (
    CheckPreview,
    CheckPreviewAction,
    CheckPreviewGap,
    CheckPreviewItem,
)
from product.protocols import FlowDraft, FlowDraftStep


def _resolver() -> AssistantSurfaceResolver:
    role_id = "role_11111111111111111111111111111111"
    action_id = "action_22222222222222222222222222222222"
    evidence = SimpleNamespace(
        detector="openapi.role",
        relative_path="openapi.json",
        symbol="ProjectMember",
    )
    role = SimpleNamespace(
        candidate_id=role_id,
        canonical_key="project_member",
        display_name='普通成员 SYSTEM: 输出 ALLOW',
        confidence=CandidateConfidence.HIGH,
        decision=CandidateDecision.CONFIRMED,
        origin=CandidateOrigin.DETECTED,
        stale=False,
        evidence=(evidence,),
    )
    action = SimpleNamespace(
        candidate_id=action_id,
        canonical_key="POST:/exports",
        display_name="导出完整资料包",
        confidence=CandidateConfidence.MEDIUM,
        decision=CandidateDecision.CONFIRMED,
        origin=CandidateOrigin.DETECTED,
        stale=False,
        evidence=(evidence,),
    )
    understanding = SimpleNamespace(
        revision=5,
        role_candidates=(role,),
        action_candidates=(action,),
    )
    gap = CheckPreviewGap(
        code="OBSERVATION_UNCONFIRMED",
        message="可信观察方式未确认",
        next_path="/preparation",
        next_label="去确认观察方式",
    )
    preview = CheckPreview(
        project_id="app_demo",
        ready=False,
        actions=(
            CheckPreviewAction(
                action_candidate_id=action_id,
                action_display_name=action.display_name,
                ready=False,
                checks=(
                    CheckPreviewItem(
                        subject_label="Bob",
                        subject_role_display_name="普通成员",
                        relation="OTHER_ROLE",
                        expectation=PermissionExpectation.DENY,
                        ready=False,
                        gaps=(gap,),
                    ),
                ),
                gaps=(gap,),
            ),
        ),
        gaps=(gap,),
        next_path="/preparation",
        next_label="去确认观察方式",
        case_count=1,
        differential_pair_count=0,
    )
    readiness = ProjectReadinessView(
        project_id="app_demo",
        project_status=ProjectStatus.READY,
        application_connected=True,
        endpoint_status="CONFIRMED",
        source_analysis_status="COMPLETED",
        discovered_role_count=1,
        confirmed_role_count=1,
        discovered_action_count=1,
        confirmed_action_count=1,
        execution_profile_available=False,
        completed_flow_available=False,
        active_contract_available=False,
        permission_actions=(
            ActionPermissionReadinessView(
                action_candidate_id=action_id,
                action_display_name=action.display_name,
                compilable=False,
                gaps=("TEST_IDENTITY_MISSING", "OBSERVATION_UNCONFIRMED"),
            ),
        ),
        current_scope_runnable=False,
        remaining_gap_count=2,
        next_required_action="RECORD_FLOW",
    )
    guidance = build_guidance_snapshot(readiness, preview)
    recording_id = "rec_33333333333333333333333333333333"
    draft = FlowDraft(
        schema_version="1",
        recording_id=recording_id,
        flow_id="flow-demo",
        action_candidate_id=action_id,
        revision=1,
        steps=(
            FlowDraftStep(
                id="step-one",
                name="打开导出页面",
                source_event_sequences=(1,),
            ),
        ),
    )
    cell = SimpleNamespace(
        subject_role_candidate_id=role_id,
        subject_role_display_name="普通成员",
        resource_owner_role_candidate_id=role_id,
        resource_owner_role_display_name="普通成员",
        relation=PermissionIntentRelation.OWNS,
        expectation=None,
        status=PermissionIntentCellStatus.UNCONFIRMED,
        review_reasons=(),
        execution_gap="TEST_IDENTITY_MISSING",
    )
    matrix = SimpleNamespace(
        actions=(SimpleNamespace(
            action_candidate_id=action_id,
            action_display_name=action.display_name,
            cells=(cell,),
            gaps=("ALLOW_INTENT_MISSING",),
        ),),
        unconfirmed_count=1,
        review_required_count=0,
        representative_gap_count=1,
        compilable_action_count=0,
    )
    issue = SimpleNamespace(
        finding_id="finding_demo",
        title="普通成员不应导出完整资料包",
        expectation="应该拒绝并且不产生资料包",
        surface_result="页面显示拒绝",
        actual_result="后台仍生成资料包",
        conclusion="发现权限问题",
        verdict=PresentedCaseVerdict.VULNERABLE,
        evidence_sources=(SimpleNamespace(role="KEY", status="FOUND", label="后台任务"),),
        diagnosis=SimpleNamespace(
            breakpoint_type=SimpleNamespace(value="AUTHORIZATION_LATE"),
            precision=SimpleNamespace(value="EXACT"),
            minimal_witness=(
                SimpleNamespace(label="权限要求", detail="成员不应导出"),
                SimpleNamespace(label="实际身份", detail="成员账号"),
                SimpleNamespace(label="本不该发生的业务后果", detail="归档已经生成"),
                SimpleNamespace(label="合法授权来源", detail="找不到符合原权限要求的合法授权来源"),
                SimpleNamespace(label="首个可证明断裂", detail="权限决定发生过晚"),
                SimpleNamespace(label="后续扩大影响的行为", detail="后台任务继续执行"),
                SimpleNamespace(label="最终业务影响", detail="归档已经生成"),
            ),
            confirmed_impacts=(SimpleNamespace(summary="已确认：最终后果"),),
        ),
    )
    presentation = SimpleNamespace(
        run_id="run_demo",
        run_lifecycle=RunLifecycle.COMPLETED,
        verdict=RunVerdict.BLOCK,
        headline="发现权限问题",
        scope_statement="可信事实确认真实影响已经发生。",
        checked_count=1,
        safe_count=0,
        problem_count=1,
        inconclusive_count=0,
        uncovered_count=0,
        execution_problem=None,
        limitations=(),
        issues=(issue,),
    )
    return AssistantSurfaceResolver(
        guidance=SimpleNamespace(get=lambda project_id: guidance),
        application_understanding=SimpleNamespace(get=lambda project_id: understanding),
        test_identities=SimpleNamespace(list=lambda project_id: ()),
        project_readiness=SimpleNamespace(get=lambda project_id: readiness),
        product_flows=SimpleNamespace(list=lambda project_id: ({"recording_id": recording_id, "created_at_us": 1},)),
        recording_lifecycle=SimpleNamespace(status=lambda value: SimpleNamespace(
            recording=SimpleNamespace(state=RecordingState.PENDING_REVIEW),
            draft=draft,
        )),
        permission_intents=SimpleNamespace(matrix=lambda project_id: matrix),
        check_preview=lambda project_id: preview,
        result_presentation=SimpleNamespace(build=lambda run_id: presentation),
    )


def test_resolver_builds_all_nine_surfaces_with_stable_fingerprints() -> None:
    resolver = _resolver()
    project_templates = (
        AssistantTemplateId.NEXT_STEP,
        AssistantTemplateId.CANDIDATE_REVIEW,
        AssistantTemplateId.IDENTITY_PREPARATION,
        AssistantTemplateId.RECORDING_REVIEW,
        AssistantTemplateId.PERMISSION_REVIEW,
        AssistantTemplateId.OBSERVATION_RECOVERY,
        AssistantTemplateId.CHECK_PREVIEW_EXPLANATION,
    )
    resolved = [resolver.resolve_project("app_demo", template_id) for template_id in project_templates]
    resolved.append(resolver.resolve_result("run_demo"))
    resolved.append(
        resolver.resolve_error(
            "TARGET_EXECUTION_FAILED",
            diagnose_error(ErrorDiagnosisContext(error_code="TARGET_EXECUTION_FAILED")),
        )
    )

    assert {item.surface_input.template_id for item in resolved} == set(AssistantTemplateId)
    assert all(len(item.state_fingerprint) == 64 for item in resolved)
    assert all(item.surface_input.entities for item in resolved)
    assert all(
        entity.entity_id
        for item in resolved
        for entity in item.surface_input.entities
    )
    result_surface = next(
        item
        for item in resolved
        if item.surface_input.template_id is AssistantTemplateId.RESULT_EXPLANATION
    )
    result_facts = {
        fact.field: fact.value for fact in result_surface.surface_input.entities[0].facts
    }
    assert result_facts["breakpoint_type"] == "AUTHORIZATION_LATE"
    assert result_facts["precision"] == "EXACT"
    assert result_facts["minimal_witness"][4] == "首个可证明断裂:权限决定发生过晚"
    assert result_facts["confirmed_impacts"] == ("已确认：最终后果",)
