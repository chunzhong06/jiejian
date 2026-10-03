# 只根据给定事实选择唯一主任务；不接收 Repository、UoW、路径或服务，不触发读取与写入。
from __future__ import annotations
from dataclasses import dataclass
from product.backend.core.applications.models import ApplicationUnderstanding, CandidateDecision
from product.backend.core.boundaries.entities import ImplementationBindingStatus
from product.backend.core.recording.models import RecordingState
from product.backend.workflows.business_boundaries.models import BusinessBoundaryView
from product.backend.workflows.preparation.models import PreparationStatus
from product.backend.workflows.preparation.demonstrations import legal_demonstrations
from product.backend.workflows.checks.repairs.repair_text import CURRENT_TASK_TEXT
from product.backend.workflows.workspace.presentation import task_view, endpoint_status as connection_status
from product.backend.workflows.workspace.models import PrimaryTaskView


@dataclass(frozen=True, slots=True)
class CheckPreviewRequired:
    """选择过程需要的下一项只读输入；协调者显式读取后再完成同一次选择。"""
    change_id: str | None = None


def boundary_task(
    understanding: ApplicationUnderstanding,
    boundary: BusinessBoundaryView,
    pending,
) -> PrimaryTaskView | None:
    endpoint_status = connection_status(understanding)
    if endpoint_status != "CONFIRMED":
        return task_view(
            "CONFIRM_APPLICATION_ENDPOINT",
            title="确认当前应用连接",
            why_now="界鉴还不能确认当前本地 Web 应用是否可以访问。",
            user_responsibility="确认或重新填写当前应用的本地访问地址。",
            system_will_do="界鉴只检查连接事实，不会向目标应用发起安全测试。",
            route="/application",
            facts={"endpoint_status": endpoint_status},
        )
    if not understanding.source_analysis_authorized:
        return task_view(
            "AUTHORIZE_SOURCE_ANALYSIS",
            title="授权只读源码分析",
            why_now="界鉴需要从当前源码整理可供你审阅的业务主体和动作线索。",
            user_responsibility="明确授权界鉴只读分析当前应用源码。",
            system_will_do="界鉴只形成候选线索，不会把候选自动当成业务权限。",
            route="/application",
            facts={"understanding_revision": understanding.revision},
        )
    if understanding.analysis_completed_at_us is None:
        return task_view(
            "RUN_SOURCE_ANALYSIS",
            title="分析当前应用源码",
            why_now="源码分析已经获得授权，但还没有形成当前候选结果。",
            user_responsibility="在应用接入页开始一次只读源码分析。",
            system_will_do="界鉴会更新候选，不会修改正式业务边界。",
            route="/application",
            facts={"understanding_revision": understanding.revision},
        )
    if pending:
        proposal = pending[0].proposal
        return task_view(
            "REVIEW_BOUNDARY_PROPOSAL",
            title="审阅待确认的业务边界",
            why_now="已有一份不可变提案等待你的明确决定。",
            user_responsibility="核对业务主体、动作、结果和权限变化，并确认或放弃提案。",
            system_will_do="只有你明确批准后，界鉴才会写入新的正式事实。",
            route="/permissions",
            facts={
                "proposal_id": proposal.proposal_id,
                "proposal_fingerprint": proposal.proposal_fingerprint,
            },
        )
    status_by_action = {
        item.action_id: item for item in boundary.permission_statuses
    }
    missing_permission = next(
        (
            item
            for item in boundary.actions
            if not status_by_action[item.action_id].permission_semantics_confirmed
            and "PERMISSION_REVISION_REVIEW_REQUIRED"
            not in status_by_action[item.action_id].reason_codes
        ),
        None,
    )
    if not boundary.actors or not boundary.actions or missing_permission is not None:
        candidates = (*understanding.role_candidates, *understanding.action_candidates)
        # 首次发现结果需有明确审阅；已有正式边界的维护不被候选建议重新阻断。
        confirmed_roles = any(item.decision is CandidateDecision.CONFIRMED and not item.stale for item in understanding.role_candidates)
        confirmed_actions = any(item.decision is CandidateDecision.CONFIRMED and not item.stale for item in understanding.action_candidates)
        if not boundary.actors and not boundary.actions and not (confirmed_roles and confirmed_actions) and any(
            item.decision is CandidateDecision.PROPOSED and not item.stale
            for item in candidates
        ):
            return task_view(
                "REVIEW_APPLICATION_CANDIDATES", title="审阅识别到的业务信息",
                why_now="源码分析已完成，候选尚未由你审阅。",
                user_responsibility="确认、排除或保留待审的权限组和业务动作。",
                system_will_do="保存候选决定后，再由你建立正式权限规则。",
                route="/application", facts={"understanding_revision": understanding.revision},
            )
        title = (
            "建立当前业务边界"
            if missing_permission is None
            else f"确认“{missing_permission.display_name}”的当前权限"
        )
        return task_view(
            "ESTABLISH_BUSINESS_BOUNDARY",
            business_action_id=(
                None if missing_permission is None else missing_permission.action_id
            ),
            title=title,
            why_now="当前还没有完整的业务动作与权限事实。",
            user_responsibility="用业务语言确认谁可以对哪些资源执行这项动作。",
            system_will_do="界鉴会先生成不可变提案，等待你再次审阅和批准。",
            route="/permissions",
            facts={
                "actor_ids": [item.actor_id for item in boundary.actors],
                "action_ids": [item.action_id for item in boundary.actions],
                "missing_action_id": (
                    None
                    if missing_permission is None
                    else missing_permission.action_id
                ),
            },
        )
    permission_review = next(
        (
            item
            for item in boundary.actions
            if {"PERMISSION_REVISION_REVIEW_REQUIRED", "PERMISSION_RELATION_REVIEW_REQUIRED"}
            & set(status_by_action[item.action_id].reason_codes)
        ),
        None,
    )
    if permission_review is not None:
        return task_view(
            "REVIEW_PERMISSION_REVISION",
            business_action_id=permission_review.action_id,
            title=f"重新确认“{permission_review.display_name}”的权限关系",
            why_now="已有权限的业务版本或资源关系需要复核，历史规则仍完整保留。",
            user_responsibility="确认操作人、资源所有者及其关系是否适用于当前业务动作。",
            system_will_do="你确认后，界鉴才写新的 Permission revision；旧规则继续保留用于历史追溯。",
            route="/permissions",
            facts={
                "action_id": permission_review.action_id,
                "action_revision": permission_review.revision,
                "reason_codes": status_by_action[
                    permission_review.action_id
                ].reason_codes,
            },
        )
    allow_missing = next((item for item in boundary.actions
                          if "ALLOW_CONTROL_REQUIRED" in status_by_action[item.action_id].reason_codes), None)
    if allow_missing is not None:
        return task_view(
            "COMPLETE_ALLOW_CONTROL", business_action_id=allow_missing.action_id,
            title=f"补充“{allow_missing.display_name}”的正常允许权限",
            why_now="准备拒绝权限的真实测试前，需要明确谁在什么资源关系下应当被允许。",
            user_responsibility="在业务边界中补充覆盖受保护业务结果的 ALLOW 权限并审阅批准。",
            system_will_do="界鉴据此编译对照身份与测试材料，不会替你猜测允许权限。",
            route="/permissions",
            facts={"action_id": allow_missing.action_id, "action_revision": allow_missing.revision,
                   "permissions": [item.model_dump(mode="json") for item in boundary.permission_intents
                                   if item.business_action_id == allow_missing.action_id]},
        )
    actor_issue = next(
        (
            item
            for item in boundary.actor_bindings
            if item.binding_exists
            and item.status is not ImplementationBindingStatus.CURRENT
        ),
        None,
    )
    if actor_issue is not None:
        actor = next(
            item for item in boundary.actors if item.actor_id == actor_issue.actor_id
        )
        return task_view(
            "REVIEW_ACTOR_IMPLEMENTATION",
            business_actor_id=actor.actor_id,
            title=f"重新确认“{actor.display_name}”的代码实现",
            why_now="原来确认的源码证据已经变化，但业务主体和权限规则仍然保持有效。",
            user_responsibility="确认当前源码中的哪项实现仍然代表这个业务主体。",
            system_will_do="界鉴只更新实现映射，不修改业务主体 revision 或权限规则。",
            route="/permissions",
            facts=actor_issue.model_dump(mode="json"),
        )
    action_issue = next(
        (
            item
            for item in boundary.action_bindings
            if item.binding_exists
            and item.status is not ImplementationBindingStatus.CURRENT
        ),
        None,
    )
    if action_issue is not None:
        action = next(
            item
            for item in boundary.actions
            if item.action_id == action_issue.action_id
        )
        return task_view(
            "REVIEW_ACTION_IMPLEMENTATION",
            business_action_id=action.action_id,
            title=f"重新确认“{action.display_name}”的代码实现",
            why_now="原来确认的源码证据已经变化，但业务动作和权限规则仍然保持有效。",
            user_responsibility="确认当前源码中的哪项实现仍然代表这项业务动作。",
            system_will_do="界鉴只更新实现映射，不修改业务动作 revision、权限规则或权限考题。",
            route="/permissions",
            facts=action_issue.model_dump(mode="json"),
        )
    return None


def allow_control_task(preparation):
    selection = next((item for item in sorted(preparation.actions, key=lambda item: item.action_id)
                      if "ALLOW_CONTROL_SELECTION_REQUIRED" in item.reason_codes), None)
    if selection is not None:
        return task_view(
            "SELECT_ALLOW_CONTROL", business_action_id=selection.action_id,
            action_revision=selection.action_revision, title="选择合法对照",
            why_now="这条权限有多个同等合适的合法对照。",
            user_responsibility="选择用于比较的合法操作。",
            system_will_do="界鉴将使用同一资源和业务结果进行比较。",
            route="/tests", facts=selection.model_dump(mode="json"),
        )
    return None


PREPARATION_TEXTS = {
    "PREPARE_TEST_IDENTITY": ("准备真实测试账号", "当前权限需要独立的真实账号。", "为指定业务主体创建账号记录，并在独立浏览器中登录。", "界鉴只安全保存当前目标所需的登录状态。"),
    "DEMONSTRATE_ACTION": ("演示一次业务动作", "当前动作还缺少可复用的业务演示。", "使用指定的正常账号完成一次业务操作。", "界鉴从实际操作中整理执行步骤与资源位置。"),
    "PREPARE_ACTION_RESOURCE": ("准备具体测试资源", "当前权限仍缺少指定账号拥有的资源。", "使用指定账号演示一次对指定资源的操作。", "界鉴保留各账号各自的资源材料。"),
    "COMPLETE_EFFECT_EVIDENCE": ("演示如何确认业务结果", "当前业务结果还缺少可观察的证明。", "演示平时在哪里确认这项业务结果。", "界鉴只关联已经确认的业务结果，不生成新请求。"),
    "COMPLETE_RECOVERY": ("演示如何恢复业务状态", "这项业务操作需要明确的恢复方式。", "演示如何恢复本次操作改变的状态。", "界鉴保存恢复材料，不运行正式安全检查。"),
}


class PreparationTaskSelection:
    """累积一个动作的纯候选；协调者在原读取位置提供已核对录制和 parent。"""

    def __init__(self, boundary, action, understanding, recordings):
        slots = sorted(action.identity_requirements.slots, key=lambda item: (item.requirement.ordinal, item.requirement.slot_id))
        slots_by_id = {item.requirement.slot_id: item for item in slots}
        prepared_ids = {item.test_identity_id for item in slots if item.status is PreparationStatus.SATISFIED}
        current_recordings = sorted((item for item in recordings
            if item.business_action_id == action.action_id and item.action_revision == action.action_revision),
            key=lambda item: (item.created_at_us, item.recording_id))
        facts = {"preparation": action.model_dump(mode="json"),
                 "source": [understanding.confirmed_endpoint, understanding.endpoint_source_fingerprint, understanding.source_fingerprint, understanding.revision],
                 "action_bindings": [item.model_dump(mode="json") for item in boundary.action_bindings if item.action_id == action.action_id],
                 "actor_bindings": [item.model_dump(mode="json") for item in boundary.actor_bindings if item.actor_id in {slot.requirement.actor_id for slot in slots}],
                 "recordings": [item.model_dump(mode="json", include={"recording_id", "state", "updated_at_us", "subject_test_identity_id", "resource_owner_test_identity_id", "preparation_source_fingerprint"}) for item in current_recordings]}
        action_current = any(item.action_id == action.action_id and item.action_revision == action.action_revision
            and item.status is ImplementationBindingStatus.CURRENT for item in boundary.action_bindings)

        self.action, self.boundary = action, boundary
        self.slots, self.slots_by_id = slots, slots_by_id
        self.prepared_ids, self.current_recordings = prepared_ids, current_recordings
        self.facts, self.action_current = facts, action_current
        self.candidates = []

    def add(self, priority, kind, *, slot=None, can_execute=True, text=None, route="/tests", **context):
        action, boundary, facts, action_current = self.action, self.boundary, self.facts, self.action_current
        title, why, responsibility, system = text or PREPARATION_TEXTS[kind]
        actor_current = slot is None or any(item.actor_id == slot.requirement.actor_id
            and item.actor_revision == slot.requirement.actor_revision
            and item.status is ImplementationBindingStatus.CURRENT for item in boundary.actor_bindings)
        if not action_current or not actor_current:
            can_execute = False
            responsibility = "请先在业务边界中确认当前实现位置。"
        if slot is not None and slot.status is PreparationStatus.STALE:
            can_execute = False
            responsibility = "请先在业务边界中复核账号所属的业务主体。"
        context = {"action_revision": action.action_revision,
            "identity_slot_id": None if slot is None else slot.requirement.slot_id,
            "test_identity_id": None if slot is None else slot.test_identity_id, **context}
        task = task_view(kind, business_action_id=action.action_id,
            business_actor_id=None if slot is None else slot.requirement.actor_id,
            title=title, why_now=why, user_responsibility=responsibility, system_will_do=system,
            route=route, facts=facts, can_execute=can_execute, **context)
        self.candidates.append(((priority, action.action_id,
            0 if slot is None else slot.requirement.ordinal, context.get("effect_id") or "",
            context.get("recording_id") or ""), task))


    def resume_recording(self, recording):
        slots = self.slots
        pending = recording.state is RecordingState.PENDING_REVIEW
        text = ("确认业务演示", "已有业务演示等待确认。", "核对业务动作、资源和结果证明。", "界鉴只保存你确认的演示材料。") if pending else (
            "继续业务演示", "已有业务演示正在进行。", "回到当前演示窗口完成采集。", "界鉴继续跟踪这次演示，不重复创建任务。")
        self.add(0, "REVIEW_RECORDING", text=text,
            slot=next(item for item in slots if item.test_identity_id == recording.subject_test_identity_id),
            subject_test_identity_id=recording.subject_test_identity_id,
            resource_owner_test_identity_id=recording.resource_owner_test_identity_id,
            subject_slot_id=next(item.requirement.slot_id for item in slots if item.test_identity_id == recording.subject_test_identity_id),
            resource_owner_slot_id=next(item.requirement.slot_id for item in slots if item.test_identity_id == recording.resource_owner_test_identity_id),
            recording_id=recording.recording_id, recording_purpose=recording.purpose.value,
            parent_recording_id=recording.parent_recording_id, effect_id=recording.effect_id)

    def prepare_missing(self):
        action, boundary, slots, slots_by_id = self.action, self.boundary, self.slots, self.slots_by_id
        for slot in slots:
            if slot.status is not PreparationStatus.SATISFIED:
                self.add(1, "PREPARE_TEST_IDENTITY", slot=slot)
        demonstrations = legal_demonstrations(action.assurance_contract, boundary.permission_intents, action.identity_requirements)

        def demonstrate(priority, kind, owner_slot_id=None):
            choices = tuple(item for item in demonstrations if owner_slot_id is None or item.resource_owner_slot_id == owner_slot_id)
            chosen = next((item for item in choices if item.can_execute), choices[0] if choices else None)
            context = {} if chosen is None else chosen.model_dump(exclude={"permission", "can_execute"})
            subject = None if chosen is None else slots_by_id[chosen.subject_slot_id]
            self.add(priority, kind, slot=subject, can_execute=chosen is not None and chosen.can_execute,
                route="/permissions" if not choices else "/tests", recording_purpose="TARGET", **context)

        if action.execution.status is not PreparationStatus.SATISFIED:
            demonstrate(2, "DEMONSTRATE_ACTION")
        for resource in action.resources:
            if resource.status is not PreparationStatus.SATISFIED and action.execution.status is PreparationStatus.SATISFIED:
                demonstrate(3, "PREPARE_ACTION_RESOURCE", resource.owner_slot_id)


    def complete_materials(self, parent):
        action, slots = self.action, self.slots
        parent_slot = None if parent is None else next((item for item in slots if item.test_identity_id == parent.subject_test_identity_id), None)
        parent_owner_slot = None if parent is None else next((item for item in slots if item.test_identity_id == parent.resource_owner_test_identity_id), None)
        parent_context = {} if parent_slot is None or parent_owner_slot is None else {
            "subject_test_identity_id": parent.subject_test_identity_id,
            "resource_owner_test_identity_id": parent.resource_owner_test_identity_id,
            "subject_slot_id": parent_slot.requirement.slot_id,
            "resource_owner_slot_id": parent_owner_slot.requirement.slot_id,
        }
        for effect in sorted(action.effect_evidence, key=lambda item: item.effect_id):
            if effect.status is not PreparationStatus.SATISFIED:
                self.add(4, "COMPLETE_EFFECT_EVIDENCE", slot=parent_slot, can_execute=parent is not None, **parent_context,
                    parent_recording_id=None if parent is None else parent.recording_id,
                    recording_purpose="OBSERVATION", effect_id=effect.effect_id)
        if action.recovery.status not in {PreparationStatus.SATISFIED, PreparationStatus.NOT_REQUIRED}:
            self.add(5, "COMPLETE_RECOVERY", slot=parent_slot, can_execute=parent is not None, **parent_context,
                parent_recording_id=None if parent is None else parent.recording_id, recording_purpose="RECOVERY")


def current_check_task(task, drifted, latest_result, preview_can_execute=None):
    if (not (task is not None and task.status == "READY_TO_VERIFY") and not drifted
            and not (task is not None and task.status in {"REPAIR_REQUIRED", "NOT_VERIFIED"})
            and latest_result is None and preview_can_execute is None):
        return CheckPreviewRequired()
    kind = ("VERIFY_REPAIR" if task is not None and task.status=="READY_TO_VERIFY" else
        "REGISTER_SOURCE_CHANGE" if drifted else
        "PREPARE_AGENT_REPAIR" if task is not None and task.status in {"REPAIR_REQUIRED", "NOT_VERIFIED"} else
        "RUN_CURRENT_CHECK" if latest_result is None and preview_can_execute else
        "VIEW_CURRENT_RESULT" if latest_result is not None else None)
    if kind is not None:
        title,why,responsibility = CURRENT_TASK_TEXT[kind]
        change_id = task.change_id if kind=="VERIFY_REPAIR" else None
        run_id = latest_result.run_id if kind=="VIEW_CURRENT_RESULT" else None
        repair_fingerprint = task.contract.repair_fingerprint if kind=="PREPARE_AGENT_REPAIR" else None
        return task_view(kind,title=title,why_now=why,user_responsibility=responsibility,
            system_will_do=why,route="/changes" if kind in {"REGISTER_SOURCE_CHANGE", "PREPARE_AGENT_REPAIR"} else "/tests",
            change_id=change_id,run_id=run_id,repair_fingerprint=repair_fingerprint,
            facts=dict(change_id=change_id,run_id=run_id,repair_fingerprint=repair_fingerprint))
    return None


def development_task(primary_task, facts, boundary_attention, active_check, preview=None):
    active_task, view, delivery, verification = facts.task, facts.view, facts.delivery, facts.verification
    if not boundary_attention and active_check is None:
        if delivery is not None and view["runtime_state"] == "NOT_LOADED":
            primary_task = task_view("LOAD_DELIVERY_RUNTIME", title="让运行实例加载这批修改",
                why_now="代码已登记，但现有进程还没有加载本批源码。", user_responsibility="在交付页显式加载，再继续准备与检查。",
                system_will_do="保留应用权限和历史，核对新运行实例。", route="/changes", change_id=delivery["change_id"],
                facts={"delivery_id": delivery["delivery_id"], "task_version": active_task.version})
        elif delivery is not None and verification["run_id"] is None and (primary_task is None or primary_task.task_kind in {"RUN_CURRENT_CHECK", "VIEW_CURRENT_RESULT"}):
            if preview is None:
                return CheckPreviewRequired(delivery["change_id"])
            primary_task = task_view("RUN_CURRENT_CHECK", title="检查这批交付，沿用全部权限要求",
                why_now="这批交付尚无精确关联的检查记录。", user_responsibility="核对本批准备与检查范围。",
                system_will_do="结果归入这批交付，不借用其它批次的通过记录。", route="/tests", change_id=delivery["change_id"],
                can_execute=preview.can_execute, facts={"delivery_id": delivery["delivery_id"], "plan": preview.plan_fingerprint})
        elif primary_task is None or primary_task.task_kind == "VIEW_CURRENT_RESULT":
            primary_task = task_view("CONTINUE_DEVELOPMENT_TASK", title="继续开发，沿用已确认权限",
                why_now="本次修改与检查已分别保留，可以回原客户端继续开发。", user_responsibility="查看本次记录，或登记下一次修改。",
                system_will_do="权限要求沿用；检查结果只关联其实际执行批次。", route="/changes",
                facts={"task_id": active_task.task_id, "task_version": active_task.version})
        elif delivery is not None and primary_task.route == "/tests" and primary_task.change_id is None and primary_task.run_id is None:
            # 材料补齐仍属于本批交付；不能从准备页返回成无关联的普通检查。
            primary_task = primary_task.model_copy(update={"change_id": delivery["change_id"]})
    return primary_task
