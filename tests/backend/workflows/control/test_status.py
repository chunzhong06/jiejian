# 统一产品状态查询测试：证明 GUI 与 CLI 共用 Readiness、下一步和最近可信结果引用。

from types import SimpleNamespace

import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import ProjectStatus, RunVerdict
from product.backend.workflows.control import ProductResultQuery, ProductStatusService
from product.backend.workflows.projects.readiness import ProjectReadinessView
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


def test_empty_workspace_has_one_deterministic_connect_action() -> None:
    status = ProductStatusService(
        SimpleNamespace(list=lambda: ()),
        lambda _project_id: pytest.fail("空工作区不应读取 readiness"),
        SimpleNamespace(build=lambda _run_id: pytest.fail("空工作区不应读取结果")),
    ).get()

    assert status.project is None
    assert status.readiness is None
    assert status.next_action.action == "CONNECT_APPLICATION"
    assert status.next_action.route == "/application"
    assert [step.status for step in status.steps] == [
        "CURRENT", "UPCOMING", "UPCOMING", "UPCOMING", "UPCOMING", "EMPTY",
    ]


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
    )
    service = ProductStatusService(
        SimpleNamespace(list=lambda: (project,), get=lambda _project_id: project),
        lambda _project_id: readiness,
        SimpleNamespace(build=lambda _run_id: presentation),
    )

    status = service.get("project_demo")

    assert status.readiness is readiness
    assert status.next_action.action == readiness.next_required_action
    assert status.next_action.route == "/results"
    assert status.latest_result is not None
    assert status.latest_result.run_id == readiness.latest_verified_run_id
    assert status.latest_result.verdict is RunVerdict.BLOCK


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
