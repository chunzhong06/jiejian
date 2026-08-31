# 验证确定性 Guidance 的 runnable 范围、阻断层级与 fingerprint。

from __future__ import annotations

from product.backend.core.lifecycle import ProjectStatus
from product.backend.workflows.assistant import (
    GuidanceOptionKind,
    GuidancePhase,
    GuidancePriorityTier,
    build_guidance_snapshot,
)
from product.backend.workflows.projects.readiness import ProjectReadinessView
from product.backend.workflows.security_setup.checks import (
    CheckPreview,
    CheckPreviewAction,
    CheckPreviewGap,
)

def _guidance_readiness(
    *,
    runnable: bool,
    remaining_gap_count: int,
) -> ProjectReadinessView:
    return ProjectReadinessView(
        project_id="guide-app",
        project_status=ProjectStatus.READY,
        application_connected=True,
        endpoint_status="CONFIRMED",
        source_analysis_status="COMPLETED",
        discovered_role_count=2,
        confirmed_role_count=2,
        discovered_action_count=2,
        confirmed_action_count=2,
        execution_profile_available=runnable,
        completed_flow_available=True,
        active_contract_available=runnable,
        current_scope_runnable=runnable,
        remaining_gap_count=remaining_gap_count,
        active_tasks=(),
        latest_verified_run_id="run-guide-1" if runnable else None,
        next_required_action="RUN_CHECK" if runnable else "RECORD_FLOW",
    )

def _guidance_gap(code: str, path: str, label: str) -> CheckPreviewGap:
    return CheckPreviewGap(
        code=code,
        message=label,
        next_path=path,
        next_label=label,
    )

def test_guidance_keeps_runnable_scope_primary_and_gaps_optional() -> None:
    flow_gap = _guidance_gap(
        "OBSERVATION_UNCONFIRMED",
        "/preparation",
        "去确认观察方式",
    )
    preview = CheckPreview(
        project_id="guide-app",
        ready=True,
        actions=(
            CheckPreviewAction(
                action_candidate_id="action-delete",
                action_display_name="删除文档",
                ready=False,
                gaps=(flow_gap,),
            ),
        ),
        gaps=(flow_gap,),
        next_path="/preparation",
        next_label="去确认观察方式",
        case_count=2,
        differential_pair_count=1,
    )

    snapshot = build_guidance_snapshot(
        _guidance_readiness(runnable=True, remaining_gap_count=1),
        preview,
    )

    start = next(
        item
        for item in snapshot.options
        if item.kind is GuidanceOptionKind.START_CURRENT_CHECK
    )
    remaining = next(
        item
        for item in snapshot.options
        if item.kind is GuidanceOptionKind.RESOLVE_COVERAGE_GAP
    )
    assert snapshot.current_scope_runnable is True
    assert snapshot.remaining_gap_count == 1
    assert start.priority_tier is GuidancePriorityTier.PRIMARY
    assert remaining.priority_tier is GuidancePriorityTier.OPTIONAL

def test_guidance_only_exposes_highest_blocking_tier_and_has_semantic_fingerprint() -> None:
    identity_gap = _guidance_gap(
        "TEST_IDENTITY_MISSING",
        "/preparation",
        "去准备测试账号",
    )
    flow_gap = _guidance_gap(
        "RECOVERY_UNCONFIRMED",
        "/preparation",
        "去确认恢复方式",
    )
    preview = CheckPreview(
        project_id="guide-app",
        ready=False,
        actions=(),
        gaps=(flow_gap, identity_gap),
        next_path="/preparation",
        next_label="去准备测试账号",
        case_count=0,
        differential_pair_count=0,
    )
    readiness = _guidance_readiness(runnable=False, remaining_gap_count=2)

    first = build_guidance_snapshot(readiness, preview)
    second = build_guidance_snapshot(readiness.model_copy(), preview.model_copy())

    assert {item.route for item in first.options} == {"/preparation"}
    assert first.state_fingerprint == second.state_fingerprint


def test_guidance_routes_unified_change_review_to_changes_page() -> None:
    readiness = _guidance_readiness(
        runnable=False,
        remaining_gap_count=1,
    ).model_copy(update={"next_required_action": "REVIEW_CHANGE"})

    snapshot = build_guidance_snapshot(readiness)

    assert snapshot.phase is GuidancePhase.CHANGE_REVIEW
    assert snapshot.options[0].kind is GuidanceOptionKind.REVIEW_CHANGE
    assert snapshot.options[0].route == "/changes"
