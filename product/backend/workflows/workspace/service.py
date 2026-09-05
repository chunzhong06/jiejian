# =============================================================================
# 定位
#   1.1.1 CURRENT 工作台的单一服务端读模型服务。
#
# 职责
#   从项目、应用理解、业务边界、权限和实时实现检查形成 WorkspaceView，按固定优先级
#   生成至多一个稳定 PrimaryTask。
#
# 边界
#   服务只读既有事实，不持久化工作区或任务状态；没有 Binding row 不等同实现失效，
#   只有已存在 Binding 的 MISSING/STALE 才能形成实现复核任务。
#
# 调用链
#   Workspace API -> WorkspaceService -> repositories/BusinessBoundaryService -> WorkspaceView。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable

from product.backend.core.application_understanding import ApplicationUnderstanding
from product.backend.core.business_boundary import (
    ImplementationBindingStatus,
    boundary_sha256,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.business_boundaries.models import BusinessBoundaryView
from product.backend.workflows.business_boundaries.service import BusinessBoundaryService
from product.backend.workflows.workspace.models import (
    ActionWorkspaceView,
    ActorWorkspaceView,
    PrimaryTaskKind,
    PrimaryTaskView,
    WorkspaceAreaView,
    WorkspaceConnectionView,
    WorkspaceProjectView,
    WorkspaceView,
)


class WorkspaceService:
    """集中决定 CURRENT 工作区内容与唯一 PrimaryTask，前端只负责渲染。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        business_boundaries: BusinessBoundaryService,
    ) -> None:
        self._uow_factory = uow_factory
        self._business_boundaries = business_boundaries

    def get(self, project_id: str) -> WorkspaceView:
        with self._uow_factory() as work:
            project = work.projects.get(project_id)
            understanding = work.application_understanding.get(project_id)
        if project is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
        if understanding is None:
            raise JiejianError(
                ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                "应用理解记录不存在",
            )

        boundary = self._business_boundaries.view(project_id)
        pending = self._business_boundaries.proposals(
            project_id,
            pending_only=True,
        ).proposals
        connection = WorkspaceConnectionView(
            endpoint_status=self._endpoint_status(understanding),
            source_analysis_status=self._source_status(understanding),
        )
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
            self._action_view(
                action,
                boundary,
                action_inspection[action.action_id],
                actor_inspection_by_id,
                status_by_action[action.action_id],
            )
            for action in boundary.actions
        )
        primary_task = self._primary_task(
            understanding,
            boundary,
            pending,
        )
        boundary_attention = bool(
            pending
            or not boundary.actors
            or not boundary.actions
            or any(
                not item.permission_status.permission_semantics_confirmed
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
        return WorkspaceView(
            project=WorkspaceProjectView(
                project_id=project.project_id,
                name=project.name,
                status=project.status,
                target_type=project.target_type,
            ),
            connection=connection,
            actors=actor_views,
            actions=action_views,
            primary_task=primary_task,
            areas=self._areas(boundary_attention),
        )

    @staticmethod
    def _action_view(
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

    @classmethod
    def _primary_task(
        cls,
        understanding: ApplicationUnderstanding,
        boundary: BusinessBoundaryView,
        pending,
    ) -> PrimaryTaskView | None:
        endpoint_status = cls._endpoint_status(understanding)
        if endpoint_status != "CONFIRMED":
            return cls._task(
                "CONFIRM_APPLICATION_ENDPOINT",
                title="确认当前应用连接",
                why_now="界鉴还不能确认当前本地 Web 应用是否可以访问。",
                user_responsibility="确认或重新填写当前应用的本地访问地址。",
                system_will_do="界鉴只检查连接事实，不会向目标应用发起安全测试。",
                route="/application",
                facts={"endpoint_status": endpoint_status},
            )
        if not understanding.source_analysis_authorized:
            return cls._task(
                "AUTHORIZE_SOURCE_ANALYSIS",
                title="授权只读源码分析",
                why_now="界鉴需要从当前源码整理可供你审阅的业务主体和动作线索。",
                user_responsibility="明确授权界鉴只读分析当前应用源码。",
                system_will_do="界鉴只形成候选线索，不会把候选自动当成业务权限。",
                route="/application",
                facts={"understanding_revision": understanding.revision},
            )
        if understanding.analysis_completed_at_us is None:
            return cls._task(
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
            return cls._task(
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
            title = (
                "建立当前业务边界"
                if missing_permission is None
                else f"确认“{missing_permission.display_name}”的当前权限"
            )
            return cls._task(
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
                if "PERMISSION_REVISION_REVIEW_REQUIRED"
                in status_by_action[item.action_id].reason_codes
            ),
            None,
        )
        if permission_review is not None:
            return cls._task(
                "REVIEW_PERMISSION_REVISION",
                business_action_id=permission_review.action_id,
                title=f"确认“{permission_review.display_name}”当前 revision 的权限",
                why_now="业务动作已经形成新 revision，旧权限完整保留为历史，但不能自动成为新 revision 的权限。",
                user_responsibility="确认旧权限是否继续适用于当前业务动作。",
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
            return cls._task(
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
            return cls._task(
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

    @staticmethod
    def _task(
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
    ) -> PrimaryTaskView:
        payload = {
            "task_kind": task_kind,
            "business_action_id": business_action_id,
            "business_actor_id": business_actor_id,
            "route": route,
            "facts": facts,
        }
        fingerprint = boundary_sha256(payload)
        return PrimaryTaskView(
            task_id=f"ptk_{fingerprint[:32]}",
            task_kind=task_kind,
            business_action_id=business_action_id,
            business_actor_id=business_actor_id,
            title=title,
            why_now=why_now,
            user_responsibility=user_responsibility,
            system_will_do=system_will_do,
            route=route,
            can_execute=True,
            stale_fingerprint=fingerprint,
        )

    @staticmethod
    def _endpoint_status(understanding: ApplicationUnderstanding) -> str:
        if understanding.confirmed_endpoint is None:
            return "NEEDS_CONFIRMATION"
        return "CONFIRMED" if understanding.endpoint_reachable else "UNAVAILABLE"

    @staticmethod
    def _source_status(understanding: ApplicationUnderstanding) -> str:
        if not understanding.source_analysis_authorized:
            return "NOT_AUTHORIZED"
        return "COMPLETED" if understanding.analysis_completed_at_us is not None else "PENDING"

    @staticmethod
    def _areas(boundary_attention: bool) -> tuple[WorkspaceAreaView, ...]:
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
                description="完整变化与重验主链将在后续版本重新接入。",
                route="/changes",
                status="BLOCKED",
                status_label="当前暂不可用",
            ),
            WorkspaceAreaView(
                key="tests",
                label="检查与结果",
                description="新的检查、执行与证据主链尚未重新接入。",
                route="/tests",
                status="BLOCKED",
                status_label="当前不可检查",
            ),
        )


__all__ = ["WorkspaceService"]
