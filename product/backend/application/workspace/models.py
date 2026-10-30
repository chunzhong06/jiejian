# 定义应用、权限规则、准备情况与当前任务的只读工作区投影。
# 模型不读取数据库或执行写入；页面展示的事实由对应服务提供。

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from product.backend.domain.boundaries.proposals import PROPOSAL_ID_PATTERN

from product.backend.domain.boundaries.entities import BusinessEffectDefinition
from product.backend.domain.identifiers import PROJECT_ID_PATTERN, SHA256_PATTERN
from product.backend.domain.lifecycle import ProjectStatus
from product.backend.domain.boundaries.permissions import PermissionIntentRevision
from product.backend.application.business_boundaries.inspection import (
    ActionImplementationInspection,
    ActorImplementationInspection,
)
from product.backend.application.business_boundaries.models import PermissionBoundaryStatus
from product.backend.application.checks.reading.results import CheckRunStatus
from product.backend.domain.verification.facts import TargetType


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
    "REVIEW_APPLICATION_CANDIDATES",
    "REVIEW_BOUNDARY_PROPOSAL",
    "ESTABLISH_BUSINESS_BOUNDARY",
    "REVIEW_PERMISSION_REVISION",
    "COMPLETE_ALLOW_CONTROL",
    "SELECT_ALLOW_CONTROL",
    "REVIEW_ACTOR_IMPLEMENTATION",
    "REVIEW_ACTION_IMPLEMENTATION",
    "REVIEW_RECORDING",
    "PREPARE_TEST_IDENTITY",
    "DEMONSTRATE_ACTION",
    "PREPARE_ACTION_RESOURCE",
    "COMPLETE_EFFECT_EVIDENCE",
    "COMPLETE_RECOVERY",
    "REGISTER_SOURCE_CHANGE",
    "PREPARE_AGENT_REPAIR",
    "VERIFY_REPAIR",
    "RUN_CURRENT_CHECK",
    "VIEW_CURRENT_RESULT",
    "CREATE_DEVELOPMENT_TASK",
    "CONTINUE_DEVELOPMENT_TASK",
    "LOAD_DELIVERY_RUNTIME",
]


class PrimaryTaskView(WorkspaceModel):
    task_id: str = Field(pattern=r"^ptk_[0-9a-f]{32}$")
    task_kind: PrimaryTaskKind
    proposal_id: str | None = Field(default=None, pattern=PROPOSAL_ID_PATTERN)
    action_label: str = Field(min_length=1, max_length=64)
    completion_criteria: str = Field(min_length=1, max_length=1024)
    unavailable_reason: str | None = Field(default=None, max_length=1024)
    business_action_id: str | None = None
    business_actor_id: str | None = None
    action_revision: int | None = Field(default=None, ge=1)
    identity_slot_id: str | None = None
    test_identity_id: str | None = None
    subject_test_identity_id: str | None = None
    resource_owner_test_identity_id: str | None = None
    subject_slot_id: str | None = None
    resource_owner_slot_id: str | None = None
    recording_id: str | None = None
    recording_purpose: Literal["TARGET", "OBSERVATION", "RECOVERY"] | None = None
    parent_recording_id: str | None = None
    effect_id: str | None = None
    title: str = Field(min_length=1, max_length=256)
    why_now: str = Field(min_length=1, max_length=1024)
    user_responsibility: str = Field(min_length=1, max_length=1024)
    system_will_do: str = Field(min_length=1, max_length=1024)
    route: Literal["/application", "/permissions", "/tests", "/changes"]
    change_id: str | None = None
    repair_fingerprint: str | None = Field(default=None, pattern=SHA256_PATTERN)
    run_id: str | None = None
    can_execute: bool
    stale_fingerprint: str = Field(pattern=SHA256_PATTERN)


class WorkspaceAreaView(WorkspaceModel):
    key: Literal["overview", "permissions", "changes", "tests"]
    label: str
    description: str
    route: Literal["/workspace", "/permissions", "/changes", "/tests"]
    status: Literal["READY", "NEEDS_ATTENTION", "BLOCKED"]
    status_label: str


from product.backend.application.projects.repair import ProjectRepair


class WorkspaceLatestResult(WorkspaceModel):
    run_id: str
    verdict: Literal["PASS","BLOCK","INCONCLUSIVE"]
    policy_epoch: int = Field(ge=0)
    created_at_us: int = Field(ge=0)
    summary: str


class WorkspaceSourceChange(WorkspaceModel):
    submitted_by: str | None = Field(default=None, min_length=1, max_length=128)
    change_id: str
    revalidation_status: str
    can_execute: bool
    reason: str
    created_at_us: int = Field(ge=0)


class WorkspaceJourneyStep(WorkspaceModel):
    key: Literal["connect", "rules", "prepare", "check"]
    label: str
    status: Literal["COMPLETE", "CURRENT", "PENDING", "NEEDS_REVIEW", "UNKNOWN"]


class WorkspaceJourney(WorkspaceModel):
    title: str
    primary_task_id: str | None
    action_id: str | None = None
    change_id: str | None = None
    run_id: str | None = None
    steps: tuple[WorkspaceJourneyStep, ...]


class WorkspaceDevelopment(WorkspaceModel):
    task_id: str
    context_id: str
    title: str
    goal: str
    revision: int
    version: int
    client_name: str | None = None
    latest_delivery_id: str | None = None
    latest_change_id: str | None = None
    latest_batch_number: int | None = None
    latest_run_id: str | None = None
    runtime_state: Literal["MATCHED", "NOT_LOADED", "UNCONFIRMED", "UNSUPPORTED"]


class WorkspaceView(WorkspaceModel):
    project: WorkspaceProjectView
    connection: WorkspaceConnectionView
    actors: tuple[ActorWorkspaceView, ...]
    actions: tuple[ActionWorkspaceView, ...]
    primary_task: PrimaryTaskView | None
    areas: tuple[WorkspaceAreaView, ...]
    latest_result: WorkspaceLatestResult | None = None
    source_change: WorkspaceSourceChange | None = None
    repair: ProjectRepair | None = None
    active_check: CheckRunStatus | None = None
    journey: WorkspaceJourney | None = None
    development: WorkspaceDevelopment | None = None


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
