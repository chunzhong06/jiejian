# 从已经选定的工作区事实生成展示模型；文案不进入任务身份，不重新判断权限或准备状态。
from __future__ import annotations
from product.backend.core.applications.models import ApplicationUnderstanding
from product.backend.core.boundaries.entities import ImplementationBindingStatus, boundary_sha256
from product.backend.core.boundaries.semantics import PermissionExpectation
from product.backend.workflows.workspace.models import ActionWorkspaceView, ActorWorkspaceView, PrimaryTaskKind, PrimaryTaskView, WorkspaceAreaView, WorkspaceJourney, WorkspaceJourneyStep

_TASK_PRESENTATION: dict[str, tuple[str, str]] = {
    "CREATE_DEVELOPMENT_TASK": ("开始下一项开发", "任务目标和沿用权限已形成可交给客户端的上下文。"),
    "CONTINUE_DEVELOPMENT_TASK": ("继续开发与交付", "每批修改保留独立交付、检查和后续处理记录。"),
    "LOAD_DELIVERY_RUNTIME": ("加载本批运行", "受控进程已加载这批源码，随后再进行完整检查。"),
    "CONFIRM_APPLICATION_ENDPOINT": ("核对应用连接", "当前应用的访问地址已经确认。"),
    "AUTHORIZE_SOURCE_ANALYSIS": ("查看源码分析授权", "你已明确授权本次只读源码分析。"),
    "RUN_SOURCE_ANALYSIS": ("开始源码分析", "本次分析完成并形成可审阅的候选。"),
    "REVIEW_APPLICATION_CANDIDATES": ("审阅候选", "候选已明确采纳或排除，尚不代表正式权限生效。"),
    "REVIEW_BOUNDARY_PROPOSAL": ("审阅这组变更", "这份提案已经形成你的确认或放弃决定。"),
    "ESTABLISH_BUSINESS_BOUNDARY": ("建立业务权限", "业务角色、动作及对应权限已由你确认。"),
    "REVIEW_PERMISSION_REVISION": ("复核权限要求", "当前业务版本对应的权限要求已重新确认。"),
    "COMPLETE_ALLOW_CONTROL": ("补齐正常权限对照", "存在覆盖禁止效果的完整允许权限。"),
    "SELECT_ALLOW_CONTROL": ("选择正常对照", "已从当前有限候选中确认一个正常对照。"),
    "REVIEW_ACTOR_IMPLEMENTATION": ("核对角色定位", "角色在当前源码中的实现定位已完成核对。"),
    "REVIEW_ACTION_IMPLEMENTATION": ("核对动作定位", "动作在当前源码中的实现定位已完成核对。"),
    "REVIEW_RECORDING": ("核对操作录制", "操作录制已审阅，并绑定到本次准备要求。"),
    "PREPARE_TEST_IDENTITY": ("准备测试账号", "账号材料已保存并通过准备核对；实际身份仍由执行事实确认。"),
    "DEMONSTRATE_ACTION": ("演示业务动作", "当前业务动作的执行材料已保存并完成核对。"),
    "PREPARE_ACTION_RESOURCE": ("准备测试资源", "本次动作所需资源已准备并完成核对。"),
    "COMPLETE_EFFECT_EVIDENCE": ("准备结果证明", "受保护业务效果的证明方式已具备。"),
    "COMPLETE_RECOVERY": ("准备恢复方式", "本次检查需要的恢复方式已明确。"),
    "REGISTER_SOURCE_CHANGE": ("查看变化登记", "本次源码变化已登记并完成实际变化核对。"),
    "PREPARE_AGENT_REPAIR": ("准备 Agent 修复任务", "Agent 完成修改并登记真实变化后，再按原题独立复验。"),
    "VERIFY_REPAIR": ("核对原题复验", "原题适用性与复验条件已经核对；修复结果由独立复验确认。"),
    "RUN_CURRENT_CHECK": ("查看检查预览", "正式预览允许执行，并由你明确开始检查。"),
    "VIEW_CURRENT_RESULT": ("查看检查结果", "本次已发布的结果与证据可供查看。"),
}


def task_view(
    task_kind: PrimaryTaskKind,
    *,
    title: str,
    why_now: str,
    user_responsibility: str,
    system_will_do: str,
    route: str,
    facts: dict,
    business_action_id: str | None = None,
    business_actor_id: str | None = None,
    can_execute: bool = True,
    **context,
) -> PrimaryTaskView:
    payload = {
        "task_kind": task_kind,
        "business_action_id": business_action_id,
        "business_actor_id": business_actor_id,
        "route": route,
        "facts": facts,
        "context": context,
        "can_execute": can_execute,
    }
    fingerprint = boundary_sha256(payload)
    # 操作文案只解释已选任务；不进入事实指纹，也不增加执行权限。
    action_label, completion = _TASK_PRESENTATION[task_kind]
    return PrimaryTaskView(
        task_id=f"ptk_{fingerprint[:32]}",
        task_kind=task_kind,
        proposal_id=facts.get("proposal_id") if task_kind == "REVIEW_BOUNDARY_PROPOSAL" else None,
        action_label=action_label,
        completion_criteria=completion,
        unavailable_reason=None if can_execute else why_now,
        business_action_id=business_action_id,
        business_actor_id=business_actor_id,
        title=title,
        why_now=why_now,
        user_responsibility=user_responsibility,
        system_will_do=system_will_do,
        route=route,
        can_execute=can_execute,
        stale_fingerprint=fingerprint,
        **context,
    )


def journey_view(connection, boundary_attention, preparation_complete, task, result, change, active):
    """只把已有事实投影为位置提示，不以位置顺序反推完成或另选主任务。"""
    connected = connection.endpoint_status == "CONFIRMED" and connection.source_analysis_status == "COMPLETED"
    kind = task.task_kind if task else None
    needs_source_review = kind == "REGISTER_SOURCE_CHANGE"
    rules_current = connected and not boundary_attention
    result_current = result is not None and rules_current and preparation_complete and not needs_source_review and kind in {None, "VIEW_CURRENT_RESULT"}
    statuses = {
        "connect": "COMPLETE" if connected else "PENDING",
        "rules": "COMPLETE" if rules_current else "NEEDS_REVIEW" if connected else "PENDING",
        "prepare": "COMPLETE" if rules_current and preparation_complete and not needs_source_review else "PENDING",
        "check": ("COMPLETE" if result_current else "NEEDS_REVIEW") if result is not None else "PENDING",
    }
    if kind in {"REVIEW_APPLICATION_CANDIDATES", "ESTABLISH_BUSINESS_BOUNDARY"}:
        statuses["rules"] = "PENDING"
    if needs_source_review:
        statuses["prepare"] = "NEEDS_REVIEW"
        statuses["check"] = "NEEDS_REVIEW"
    if task:
        current = ("connect" if task.route == "/application" else "rules" if task.route == "/permissions" else
            "check" if kind in {"RUN_CURRENT_CHECK", "VIEW_CURRENT_RESULT", "VERIFY_REPAIR", "PREPARE_AGENT_REPAIR"} else "prepare")
        statuses[current] = "CURRENT"
    # 活动 Run 可在其他待办出现时继续运行；只提示进度，不能据此完成前三项。
    if active is not None and task is None:
        statuses["check"] = "CURRENT"
    title = "核对代码变化后的权限" if change or needs_source_review else "建立本次权限检查"
    return WorkspaceJourney(title=title, primary_task_id=task.task_id if task else None,
        action_id=task.business_action_id if task else None,
        change_id=change.change_id if change else None,
        run_id=active.run.run_id if active else result.run_id if result else None,
        steps=tuple(WorkspaceJourneyStep(key=key, label=label, status=statuses[key]) for key, label in (
            ("connect", "接入应用"), ("rules", "确认规则"), ("prepare", "准备检查"), ("check", "检查与结果"))))


def action_view(
    action,
    boundary: BusinessBoundaryView,
    inspection,
    actor_inspection_by_id,
    permission_status,
) -> ActionWorkspaceView:
    permissions = tuple(
        item
        for item in boundary.permission_intents
        if item.business_action_id == action.action_id
        and item.action_revision == action.revision
    )
    actor_ids = tuple(
        sorted(
            {
                actor_id
                for item in permissions
                for actor_id in (
                    item.subject_actor_id,
                    item.resource_owner_actor_id,
                )
            }
        )
    )
    actor_issues = sum(
        actor_inspection_by_id[actor_id].binding_exists
        and actor_inspection_by_id[actor_id].status
        is not ImplementationBindingStatus.CURRENT
        for actor_id in actor_ids
        if actor_id in actor_inspection_by_id
    )
    return ActionWorkspaceView(
        action_id=action.action_id,
        action_revision=action.revision,
        display_name=action.display_name,
        description=action.description,
        effect_catalog=action.effect_catalog,
        current_permissions=permissions,
        permission_status=permission_status,
        implementation=inspection,
        subject_actor_ids=actor_ids,
        actor_implementation_issue_count=actor_issues,
    )


def endpoint_status(understanding: ApplicationUnderstanding) -> str:
    if understanding.confirmed_endpoint is None:
        return "NEEDS_CONFIRMATION"
    return "CONFIRMED" if understanding.endpoint_reachable else "UNAVAILABLE"


def source_status(understanding: ApplicationUnderstanding) -> str:
    if not understanding.source_analysis_authorized:
        return "NOT_AUTHORIZED"
    return "COMPLETED" if understanding.analysis_completed_at_us is not None else "PENDING"


def area_views(boundary_attention: bool, preparation_complete: bool) -> tuple[WorkspaceAreaView, ...]:
    from product.backend.workflows.checks.repairs.repair_text import CURRENT_TASK_TEXT
    return (
        WorkspaceAreaView(
            key="overview",
            label="工作台",
            description="查看当前应用、唯一主任务与业务动作状态。",
            route="/workspace",
            status="READY",
            status_label="持续更新",
        ),
        WorkspaceAreaView(
            key="permissions",
            label="业务边界",
            description="建立并持续维护业务主体、动作、结果与权限。",
            route="/permissions",
            status="NEEDS_ATTENTION" if boundary_attention else "READY",
            status_label="需要处理" if boundary_attention else "当前已确认",
        ),
        WorkspaceAreaView(
            key="changes",
            label="变化与修复",
            description=CURRENT_TASK_TEXT["REGISTER_SOURCE_CHANGE"][1],
            route="/changes",
            status="NEEDS_ATTENTION" if boundary_attention else "READY",
            status_label="需要处理" if boundary_attention else "当前已确认",
        ),
        WorkspaceAreaView(
            key="tests",
            label="检查与结果",
            description=CURRENT_TASK_TEXT["RUN_CURRENT_CHECK"][1],
            route="/tests",
            status="READY" if preparation_complete else "NEEDS_ATTENTION",
            status_label="材料已准备" if preparation_complete else "需要准备",
        ),
    )


def boundary_views(boundary, pending):
    actor_inspection = {
        item.actor_id: item for item in boundary.actor_bindings
    }
    action_inspection = {
        item.action_id: item for item in boundary.action_bindings
    }
    actor_views = tuple(
        ActorWorkspaceView(
            actor_id=actor.actor_id,
            actor_revision=actor.revision,
            display_name=actor.display_name,
            description=actor.description,
            implementation=actor_inspection[actor.actor_id],
            current_permission_reference_count=sum(
                actor.actor_id
                in (permission.subject_actor_id, permission.resource_owner_actor_id)
                for permission in boundary.permission_intents
            ),
        )
        for actor in boundary.actors
    )
    actor_inspection_by_id = {
        item.actor_id: item.implementation for item in actor_views
    }
    status_by_action = {
        item.action_id: item for item in boundary.permission_statuses
    }
    action_views = tuple(
        action_view(
            action,
            boundary,
            action_inspection[action.action_id],
            actor_inspection_by_id,
            status_by_action[action.action_id],
        )
        for action in boundary.actions
    )
    boundary_attention = bool(
        pending
        or not boundary.actors
        or not boundary.actions
        or any(
            not item.permission_status.permission_semantics_confirmed
            or bool(item.permission_status.reason_codes)
            or item.implementation.status is not ImplementationBindingStatus.CURRENT
            and item.implementation.binding_exists
            or item.actor_implementation_issue_count
            for item in action_views
        )
        or any(
            item.implementation.binding_exists
            and item.implementation.status is not ImplementationBindingStatus.CURRENT
            for item in actor_views
        )
    )
    return actor_views, action_views, boundary_attention


def development_view(facts):
    from product.backend.workflows.workspace.models import WorkspaceDevelopment
    active_task, view, delivery, verification = facts.task, facts.view, facts.delivery, facts.verification
    return WorkspaceDevelopment(task_id=active_task.task_id, context_id=active_task.context_id,
        title="继续开发，沿用已确认权限", goal=view["context"]["goal"], revision=active_task.revision, version=active_task.version,
        client_name=None if view["acceptance"] is None else view["acceptance"]["client_name"],
        latest_delivery_id=None if delivery is None else delivery["delivery_id"],
        latest_change_id=None if delivery is None else delivery["change_id"],
        latest_batch_number=None if delivery is None else delivery["ordinal"],
        latest_run_id=None if verification is None else verification["run_id"], runtime_state=view["runtime_state"])
