# 持续验证状态查询测试：证明 GUI 与 CLI 共用工作区、待办、变化和可信结果引用。

from types import SimpleNamespace

import pytest

from product.backend.core.errors import JiejianError
from product.backend.core.lifecycle import ProjectStatus, RunVerdict
from product.backend.core.repair import RepairContractReference
from product.backend.workflows.control import ProductResultQuery, ProductStatusService
from product.backend.workflows.projects.readiness import (
    ActionPermissionReadinessView,
    ActiveTaskView,
    ProjectReadinessView,
)
from product.backend.workflows.projects.preparation import (
    PreparationItemKind,
    PreparationItemStatus,
    PreparationItemView,
    ProjectPreparationView,
)
from product.backend.workflows.projects.revalidation import (
    ProjectRevalidationStatus,
    ProjectRevalidationView,
)
from product.backend.workflows.projects.repair import (
    ProjectRepairStatus,
    ProjectRepairView,
    RepairTaskView,
)
from product.backend.workflows.source_changes import SourceChangeView
from product.protocols import TargetType


INTENT_ID = f"pin_{'1' * 32}"
INTENT_HASH = "a" * 64


def _preparation(*, ready: bool) -> ProjectPreparationView:
    status = PreparationItemStatus.READY if ready else PreparationItemStatus.USER
    item = PreparationItemView(
        key="flow:action_demo",
        kind=PreparationItemKind.FLOW,
        label="导出完整包业务流程",
        status=status,
        description="业务流程已经准备。" if ready else "需要录制真实业务流程。",
        next_path=None if ready else "/flows",
        next_label=None if ready else "管理业务流程",
        reason_codes=() if ready else ("COMPLETED_FLOW_MISSING",),
        action_candidate_id="action_demo",
    )
    return ProjectPreparationView(
        project_id="project_demo",
        ready=ready,
        items=(item,),
        next_item_key=None if ready else item.key,
        auto_action_count=0,
        user_action_count=0 if ready else 1,
        blocked_count=0,
        external_blockers=(),
    )


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
        preparation=_preparation(ready=True),
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
    revalidation = ProjectRevalidationView(
        project_id="project_demo",
        status=ProjectRevalidationStatus.REVIEW_REQUIRED,
        change_id=change.change_id,
        summary="最近变化的实现映射需要重新确认。",
        next_path="/permissions",
        next_label="确认权限实现",
        required_intent_count=1,
        reason_codes=("MAPPING_REVIEW_REQUIRED",),
        verified_run_id="run_demo",
        verified_change_id=change.change_id,
    )
    service = ProductStatusService(
        SimpleNamespace(list=lambda: (project,), get=lambda _project_id: project),
        lambda _project_id: readiness,
        SimpleNamespace(build=lambda _run_id: presentation),
        SimpleNamespace(latest_view=lambda _project_id: change),
        project_revalidation=SimpleNamespace(
            evaluate=lambda *_args, **_kwargs: revalidation
        ),
    )

    status = service.get("project_demo")

    assert status.readiness is readiness
    assert status.revalidation is revalidation
    assert status.latest_change is change
    assert status.areas[1].status == "NEEDS_ATTENTION"
    assert status.areas[2].status == "NEEDS_ATTENTION"
    assert status.areas[4].status == "BLOCKED"
    assert any(item.key == "review-change-mapping" for item in status.attention_items)
    assert status.latest_result is not None
    assert status.latest_result.run_id == readiness.latest_verified_run_id
    assert status.latest_result.verdict is RunVerdict.BLOCK
    assert status.latest_result.verified_change_id == change.change_id


def test_latest_result_and_cross_run_project_repair_remain_independent() -> None:
    readiness = _readiness(action="OPEN_RESULT", latest_run_id="run_demo")
    project = _project()
    presentation = _presentation(RunVerdict.PASS, (_intent(),))
    repair = _repair(ProjectRepairStatus.REPAIR_REQUIRED, "/results")
    received: list[dict[str, object]] = []

    def evaluate(_project_id: str, **kwargs):
        received.append(kwargs)
        return repair

    service = ProductStatusService(
        SimpleNamespace(list=lambda: (project,), get=lambda _project_id: project),
        lambda _project_id: readiness,
        SimpleNamespace(build=lambda _run_id: presentation),
        project_repair=SimpleNamespace(evaluate=evaluate),
    )

    status = service.get("project_demo")

    assert status.latest_result is not None
    assert status.latest_result.verdict is RunVerdict.PASS
    assert status.repair is repair
    assert len(received) == 1
    assert "latest_presentation" not in received[0]


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
            "preparation": _preparation(ready=False),
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


@pytest.mark.parametrize("verdict", [RunVerdict.PASS, RunVerdict.BLOCK])
def test_non_inconclusive_latest_result_has_no_recovery(verdict: RunVerdict) -> None:
    status = _recovery_service(
        verdict=verdict,
        source_intents=(_intent(),),
        current_intents=(_intent(),),
    ).get("project_demo")

    assert status.inconclusive_recovery is None


def test_exact_original_exam_and_ready_preparation_offer_new_validation_run() -> None:
    status = _recovery_service(
        source_intents=(_intent(),),
        current_intents=(_intent(),),
    ).get("project_demo")

    recovery = status.inconclusive_recovery
    assert recovery is not None
    assert recovery.source_run_id == "run_demo"
    assert recovery.next_path == "/validation"
    assert recovery.next_label == "重新检查原权限考题"
    assert "新的独立检查" in recovery.summary
    assert any(item.key == "recover-inconclusive" for item in status.attention_items)


@pytest.mark.parametrize(
    "current_intents",
    [
        (SimpleNamespace(intent_id=INTENT_ID, revision=2, intent_hash=INTENT_HASH),),
        (SimpleNamespace(intent_id=INTENT_ID, revision=1, intent_hash="b" * 64),),
        (
            SimpleNamespace(
                intent_id=INTENT_ID,
                revision=1,
                intent_hash=INTENT_HASH,
            ),
            SimpleNamespace(
                intent_id=f"pin_{'2' * 32}",
                revision=1,
                intent_hash="c" * 64,
            ),
        ),
    ],
)
def test_changed_revision_hash_or_set_cannot_claim_original_exam_recheck(
    current_intents,
) -> None:
    status = _recovery_service(
        source_intents=(_intent(),),
        current_intents=current_intents,
    ).get("project_demo")

    recovery = status.inconclusive_recovery
    assert recovery is not None
    assert recovery.next_path == "/permissions"
    assert recovery.next_label == "查看当前权限规则"
    assert recovery.reason_codes == ("ORIGINAL_PERMISSION_INTENT_CHANGED",)
    assert "原题复验" in recovery.summary


@pytest.mark.parametrize(
    ("revalidation_status", "next_path"),
    [
        (ProjectRevalidationStatus.REVIEW_REQUIRED, "/permissions"),
        (ProjectRevalidationStatus.STALE, "/changes"),
    ],
)
def test_change_review_precedes_inconclusive_recovery(
    revalidation_status: ProjectRevalidationStatus,
    next_path: str,
) -> None:
    revalidation = ProjectRevalidationView(
        project_id="project_demo",
        status=revalidation_status,
        change_id=f"chg_{'1' * 32}",
        summary="当前代码变化仍需审阅。",
        next_path=next_path,
        next_label="处理代码变化",
        required_intent_count=1,
        reason_codes=("CHANGE_REVIEW",),
    )
    status = _recovery_service(
        source_intents=(_intent(),),
        current_intents=(_intent(),),
        revalidation=revalidation,
    ).get("project_demo")

    recovery = status.inconclusive_recovery
    assert recovery is not None
    assert recovery.next_path == next_path
    assert recovery.next_label == "处理代码变化"
    assert len(
        [
            item
            for item in status.attention_items
            if item.route == next_path and item.tone != "INFO"
        ]
    ) == 1


def test_incomplete_preparation_routes_to_only_current_asset_repairs() -> None:
    status = _recovery_service(
        source_intents=(_intent(),),
        current_intents=(_intent(),),
        preparation_ready=False,
    ).get("project_demo")

    recovery = status.inconclusive_recovery
    assert recovery is not None
    assert recovery.next_path == "/preparation"
    assert recovery.next_label == "修复测试准备"
    assert len(
        [item for item in status.attention_items if item.route == "/preparation"]
    ) == 1


def test_unfinished_repair_precedes_same_route_revalidation_attention() -> None:
    revalidation = ProjectRevalidationView(
        project_id="project_demo",
        status=ProjectRevalidationStatus.REVIEW_REQUIRED,
        change_id=f"chg_{'1' * 32}",
        summary="当前修复变化仍需确认实现映射。",
        next_path="/permissions",
        next_label="确认权限实现",
        required_intent_count=1,
        reason_codes=("MAPPING_REVIEW_REQUIRED",),
    )
    status = _recovery_service(
        verdict=RunVerdict.BLOCK,
        revalidation=revalidation,
        repair=_repair(ProjectRepairStatus.CHANGE_SUBMITTED, "/permissions"),
    ).get("project_demo")

    warnings = [
        item
        for item in status.attention_items
        if item.route == "/permissions" and item.tone != "INFO"
    ]
    assert [item.key for item in warnings] == ["continue-project-repair"]


def test_inconclusive_repair_reuses_recovery_route_without_duplicate_attention() -> None:
    status = _recovery_service(
        source_intents=(_intent(),),
        current_intents=(
            SimpleNamespace(intent_id=INTENT_ID, revision=2, intent_hash=INTENT_HASH),
        ),
        repair=_repair(ProjectRepairStatus.INCONCLUSIVE, "/preparation"),
    ).get("project_demo")

    assert status.repair is not None
    assert status.repair.next_path == "/permissions"
    assert status.repair.tasks[0].next_path == "/permissions"
    assert status.repair.reason_codes == (
        "REPAIR_INCONCLUSIVE",
        "ORIGINAL_PERMISSION_INTENT_CHANGED",
    )
    assert len(
        [
            item
            for item in status.attention_items
            if item.route == "/permissions" and item.tone != "INFO"
        ]
    ) == 1


def test_recovery_projection_repeated_reads_have_no_write_callback() -> None:
    calls = {"presentation": 0, "intents": 0}
    presentation = _presentation(RunVerdict.INCONCLUSIVE, (_intent(),))

    def build(_run_id):
        calls["presentation"] += 1
        return presentation

    def current(_project_id):
        calls["intents"] += 1
        return (_intent(),)

    project = _project()
    service = ProductStatusService(
        SimpleNamespace(list=lambda: (project,), get=lambda _project_id: project),
        lambda _project_id: _readiness(action="OPEN_RESULT", latest_run_id="run_demo"),
        SimpleNamespace(build=build),
        current_permission_intents=current,
    )

    assert service.get("project_demo").inconclusive_recovery is not None
    assert service.get("project_demo").inconclusive_recovery is not None
    assert calls == {"presentation": 2, "intents": 2}


def _intent():
    return SimpleNamespace(
        intent_id=INTENT_ID,
        revision=1,
        intent_hash=INTENT_HASH,
    )


def _project():
    return SimpleNamespace(
        project_id="project_demo",
        name="演示应用",
        status=ProjectStatus.READY,
        target_type=TargetType.WEB,
    )


def _presentation(verdict: RunVerdict, relevant_intents):
    return SimpleNamespace(
        run_id="run_demo",
        verdict=verdict,
        headline="证据不足" if verdict is RunVerdict.INCONCLUSIVE else "已有结论",
        scope_statement="当前范围已经形成可信发布结果。",
        change_verification=None,
        relevant_intents=relevant_intents,
    )


def _recovery_service(
    *,
    verdict: RunVerdict = RunVerdict.INCONCLUSIVE,
    source_intents=(),
    current_intents=(),
    preparation_ready: bool = True,
    revalidation: ProjectRevalidationView | None = None,
    repair: ProjectRepairView | None = None,
) -> ProductStatusService:
    project = _project()
    readiness = _readiness(action="OPEN_RESULT", latest_run_id="run_demo").model_copy(
        update={
            "preparation": _preparation(ready=preparation_ready),
            "current_scope_runnable": preparation_ready,
        }
    )
    return ProductStatusService(
        SimpleNamespace(list=lambda: (project,), get=lambda _project_id: project),
        lambda _project_id: readiness,
        SimpleNamespace(
            build=lambda _run_id: _presentation(verdict, source_intents)
        ),
        project_revalidation=(
            None
            if revalidation is None
            else SimpleNamespace(evaluate=lambda *_args, **_kwargs: revalidation)
        ),
        project_repair=(
            None
            if repair is None
            else SimpleNamespace(evaluate=lambda *_args, **_kwargs: repair)
        ),
        current_permission_intents=lambda _project_id: current_intents,
    )


def _repair(status: ProjectRepairStatus, next_path: str) -> ProjectRepairView:
    reference = RepairContractReference(
        source_run_id="run_" + "d" * 32,
        source_finding_id="finding_" + "e" * 32,
        repair_fingerprint="d" * 64,
    )
    task = RepairTaskView(
        reference=reference,
        source_run_id=reference.source_run_id,
        source_finding_id=reference.source_finding_id,
        status=status,
        must_disappear="越权业务后果必须消失。",
        must_remain="合法业务路径必须保留。",
        must_not_change=("原权限考题", "受保护业务后果"),
        next_path=next_path,
        next_label="继续处理当前修复",
        reason_codes=(f"REPAIR_{status.value}",),
    )
    return ProjectRepairView(
        project_id="project_demo",
        status=status,
        tasks=(task,),
        next_path=next_path,
        next_label=task.next_label,
        reason_codes=task.reason_codes,
    )
