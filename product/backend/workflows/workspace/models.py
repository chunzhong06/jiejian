# =============================================================================
# 定位
#   1.1.1 当前动作级工作区的只读模型合同。
#
# 职责
#   统一承载项目连接、业务主体、业务动作、权限、实时实现检查和唯一主任务。
#
# 边界
#   这里只定义投影模型；不读取数据库、不推导页面本地状态，也不提供写入命令。
#
# 调用链
#   WorkspaceService -> WorkspaceView -> Workspace API -> CURRENT Web 工作台。
# =============================================================================

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.business_boundary import (
    BusinessEffectDefinition,
    BusinessActionRevision,
    BusinessActorRevision,
)
from product.backend.core.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.permission_intent import PermissionIntentRevision
from product.backend.workflows.business_boundaries.inspection import (
    ActionImplementationInspection,
    ActorImplementationInspection,
)
from product.backend.workflows.business_boundaries.models import PermissionBoundaryStatus
from product.protocols import TargetType


class WorkspaceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, strict=True, hide_input_in_errors=True
    )


class WorkspaceProjectView(WorkspaceModel):
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=256)
    status: ProjectStatus
    target_type: TargetType


class WorkspaceConnectionView(WorkspaceModel):
    endpoint_status: Literal["NEEDS_CONFIRMATION", "CONFIRMED", "UNAVAILABLE"]
    source_analysis_status: Literal["NOT_AUTHORIZED", "PENDING", "COMPLETED"]


class ActorWorkspaceView(WorkspaceModel):
    actor_id: str
    actor_revision: int = Field(ge=1)
    display_name: str
    description: str
    implementation: ActorImplementationInspection
    current_permission_reference_count: int = Field(ge=0)


class ActionWorkspaceView(WorkspaceModel):
    action_id: str
    action_revision: int = Field(ge=1)
    display_name: str
    description: str
    effect_catalog: tuple[BusinessEffectDefinition, ...]
    current_permissions: tuple[PermissionIntentRevision, ...]
    permission_status: PermissionBoundaryStatus
    implementation: ActionImplementationInspection
    subject_actor_ids: tuple[str, ...]
    actor_implementation_issue_count: int = Field(ge=0)


PrimaryTaskKind = Literal[
    "CONFIRM_APPLICATION_ENDPOINT",
    "AUTHORIZE_SOURCE_ANALYSIS",
    "RUN_SOURCE_ANALYSIS",
    "REVIEW_BOUNDARY_PROPOSAL",
    "ESTABLISH_BUSINESS_BOUNDARY",
    "REVIEW_PERMISSION_REVISION",
    "REVIEW_ACTOR_IMPLEMENTATION",
    "REVIEW_ACTION_IMPLEMENTATION",
]


class PrimaryTaskView(WorkspaceModel):
    task_id: str = Field(pattern=r"^ptk_[0-9a-f]{32}$")
    task_kind: PrimaryTaskKind
    business_action_id: str | None = None
    business_actor_id: str | None = None
    title: str = Field(min_length=1, max_length=256)
    why_now: str = Field(min_length=1, max_length=1024)
    user_responsibility: str = Field(min_length=1, max_length=1024)
    system_will_do: str = Field(min_length=1, max_length=1024)
    route: Literal["/application", "/permissions"]
    can_execute: bool
    stale_fingerprint: str = Field(pattern=SHA256_PATTERN)


class WorkspaceAreaView(WorkspaceModel):
    key: Literal["overview", "permissions", "changes", "tests"]
    label: str
    description: str
    route: Literal["/workspace", "/permissions", "/changes", "/tests"]
    status: Literal["READY", "NEEDS_ATTENTION", "BLOCKED"]
    status_label: str


class WorkspaceView(WorkspaceModel):
    project: WorkspaceProjectView
    connection: WorkspaceConnectionView
    actors: tuple[ActorWorkspaceView, ...]
    actions: tuple[ActionWorkspaceView, ...]
    primary_task: PrimaryTaskView | None
    areas: tuple[WorkspaceAreaView, ...]


__all__ = [
    "ActionWorkspaceView",
    "ActorWorkspaceView",
    "PrimaryTaskKind",
    "PrimaryTaskView",
    "WorkspaceAreaView",
    "WorkspaceConnectionView",
    "WorkspaceProjectView",
    "WorkspaceView",
]
