# 持续验证状态查询测试：证明 GUI 与 CLI 共用工作区、待办、变化和可信结果引用。

from types import SimpleNamespace

import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import ProjectStatus, RunVerdict
from product.backend.workflows.control import ProductResultQuery, ProductStatusService
from product.backend.workflows.projects.readiness import (
    ActionPermissionReadinessView,
    ActiveTaskView,
    ProjectReadinessView,
)
from product.backend.workflows.source_changes import SourceChangeView
from product.protocols import TargetType


def _readiness(*, action: str, latest_run_id: str | None = None) -> ProjectReadinessView:
    return ProjectReadinessView(
        project_id="project_demo",
        project_status=ProjectStatus.READY,
        application_connected=True,
        endpoint_status="CONFIRMED",
        source_analysis_status="COMPLETED",
        discovered_role_count=2,
        confirmed_role_count=2,
        discovered_action_count=1,
        confirmed_action_count=1,
        execution_profile_available=True,
        completed_flow_available=True,
        active_contract_available=True,
        current_scope_runnable=True,
        remaining_gap_count=0,
        latest_verified_run_id=latest_run_id,
        next_required_action=action,
    )


def _change(*, review_count: int = 1) -> SourceChangeView:
    return SourceChangeView(
        change_id=f"chg_{'1' * 32}",
        project_id="project_demo",
        reason="Agent 新增了完整包导出入口",
        created_at_us=1,
        status="COMPARABLE",
        complete=True,
        actual_changed_path_count=1,
        added_count=0,
        modified_count=1,
        removed_count=0,
        modified_paths=("app/export.py",),
        directly_affected_count=1,
        mapping_review_required_count=review_count,
        no_direct_evidence_count=0,
        review_intent_ids=(f"pin_{'2' * 32}",) if review_count else (),
        summary="有 1 条权限规则需要重新确认。" if review_count else "变化已完成对应。",
        next_path="/permissions" if review_count else None,
    )


def test_empty_workspace_offers_long_lived_areas_and_connect_attention() -> None:
    status = ProductStatusService(
        SimpleNamespace(list=lambda: ()),
        lambda _project_id: pytest.fail("空工作区不应读取 readiness"),
        SimpleNamespace(build=lambda _run_id: pytest.fail("空工作区不应读取结果")),
    ).get()

    assert status.project is None
    assert status.readiness is None
    assert status.attention_items[0].key == "connect-application"
    assert status.attention_items[0].route == "/application"
    assert [area.key for area in status.areas] == [
        "overview", "changes", "permissions", "preparation", "validation", "results",
    ]
    assert status.areas[0].status == "READY"
    assert status.areas[-1].status == "EMPTY"


def test_status_reuses_exact_readiness_and_presentation_reference() -> None:
    readiness = _readiness(action="OPEN_RESULT", latest_run_id="run_demo")
    project = SimpleNamespace(
        project_id="project_demo",
        name="演示应用",
        status=ProjectStatus.READY,
        target_type=TargetType.WEB,
    )
    presentation = SimpleNamespace(
        run_id="run_demo",
        verdict=RunVerdict.BLOCK,
        headline="发现权限问题",
        scope_statement="当前范围内确认了真实安全影响。",
        change_verification=SimpleNamespace(change_id=f"chg_{'1' * 32}"),
    )
    change = _change()
    service = ProductStatusService(
        SimpleNamespace(list=lambda: (project,), get=lambda _project_id: project),
        lambda _project_id: readiness,
        SimpleNamespace(build=lambda _run_id: presentation),
        SimpleNamespace(latest_view=lambda _project_id: change),
    )

    status = service.get("project_demo")

    assert status.readiness is readiness
    assert status.latest_change is change
    assert status.areas[1].status == "NEEDS_ATTENTION"
    assert any(item.key == "review-change-mapping" for item in status.attention_items)
    assert status.latest_result is not None
    assert status.latest_result.run_id == readiness.latest_verified_run_id
    assert status.latest_result.verdict is RunVerdict.BLOCK
    assert status.latest_result.verified_change_id == change.change_id


def test_result_query_selects_current_presentation_and_history_without_reinterpretation() -> None:
    status = SimpleNamespace(
        project=SimpleNamespace(project_id="project_demo"),
        readiness=SimpleNamespace(latest_verified_run_id="run_demo"),
    )
    presentation = object()
    history = object()
    query = ProductResultQuery(
        SimpleNamespace(get=lambda _project_id: status),
        SimpleNamespace(build=lambda run_id: presentation if run_id == "run_demo" else None),
        SimpleNamespace(build=lambda project_id: history if project_id == "project_demo" else None),
    )

    assert query.presentation(project_id="project_demo") is presentation
    assert query.history("project_demo") is history


def test_implicit_project_selection_rejects_ambiguity() -> None:
    projects = (SimpleNamespace(project_id="one"), SimpleNamespace(project_id="two"))
    service = ProductStatusService(
        SimpleNamespace(list=lambda: projects),
        lambda _project_id: pytest.fail("歧义时不应读取 readiness"),
        SimpleNamespace(build=lambda _run_id: None),
    )

    with pytest.raises(JiejianError) as raised:
        service.get()

    assert raised.value.code == "INPUT_INVALID"


def test_recording_task_and_preparation_gaps_route_back_to_preparation() -> None:
    readiness = _readiness(action="RECORD_FLOW").model_copy(
        update={
            "active_tasks": (
                ActiveTaskView(kind="RECORDING", task_id="recording_demo", state="RECORDING"),
            ),
            "permission_actions": (
                ActionPermissionReadinessView(
                    action_candidate_id="action_demo",
                    action_display_name="导出完整包",
                    compilable=False,
                    gaps=("MISSING_RESOURCE", "MISSING_OBSERVER", "RELATION_UNPROVABLE"),
                ),
            ),
            "completed_flow_available": False,
            "current_scope_runnable": False,
        }
    )
    project = SimpleNamespace(
        project_id="project_demo",
        name="演示应用",
        status=ProjectStatus.READY,
        target_type=TargetType.WEB,
    )
    status = ProductStatusService(
        SimpleNamespace(list=lambda: (project,), get=lambda _project_id: project),
        lambda _project_id: readiness,
        SimpleNamespace(build=lambda _run_id: None),
    ).get("project_demo")

    active = next(item for item in status.attention_items if item.key == "active-task")
    preparation = next(
        item for item in status.attention_items if item.key == "complete-preparation"
    )
    assert active.route == "/preparation"
    assert active.label == "查看正在录制的业务流程"
    assert preparation.route == "/preparation"
