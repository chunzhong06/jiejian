# Business Boundary 控制面 API：把 JSON DTO 转为严格领域命令。
# 不生成正式 ID、Approval 或 epoch；Approve/Reject 身份始终由服务端固定。

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.composition import ApplicationCore
from product.backend.core.boundary_proposal import (
    ProposedActionItem,
    ProposedActorItem,
    ProposedPermissionItem,
)
from product.backend.workflows.business_boundaries import (
    BoundaryMaintenanceActionItem,
    BoundaryMaintenanceActorItem,
    BoundaryMaintenanceCommand,
    BoundaryMaintenancePermissionItem,
    BoundaryProposalCommand,
)


class BoundaryProposalCreateRequest(ApiModel):
    schema_version: Literal["1"]
    proposed_actors: list[dict[str, object]] = Field(default_factory=list, max_length=256)
    proposed_actions: list[dict[str, object]] = Field(default_factory=list, max_length=512)
    proposed_permissions: list[dict[str, object]] = Field(default_factory=list, max_length=1024)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=128)
    provenance: str = Field(min_length=1, max_length=512)

    def to_command(self) -> BoundaryProposalCommand:
        """通过 JSON 模式构造严格领域对象，避免把传输 list 当成领域 tuple。"""

        return BoundaryProposalCommand(
            proposed_actors=tuple(
                ProposedActorItem.model_validate_json(_item_json(item))
                for item in self.proposed_actors
            ),
            proposed_actions=tuple(
                ProposedActionItem.model_validate_json(_item_json(item))
                for item in self.proposed_actions
            ),
            proposed_permissions=tuple(
                ProposedPermissionItem.model_validate_json(_item_json(item))
                for item in self.proposed_permissions
            ),
            unresolved_questions=tuple(self.unresolved_questions),
            provenance=self.provenance,
        )


def _item_json(item: dict[str, object]) -> str:
    return json.dumps(
        item,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class BoundaryDecisionRequest(ApiModel):
    schema_version: Literal["1"]
    expected_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=512)


class BoundaryMaintenanceCreateRequest(ApiModel):
    schema_version: Literal["1"]
    expected_boundary_state_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    actors: list[dict[str, object]] = Field(max_length=256)
    actions: list[dict[str, object]] = Field(max_length=512)
    permissions: list[dict[str, object]] = Field(max_length=1024)
    provenance: str = Field(min_length=1, max_length=512)

    def to_command(self) -> BoundaryMaintenanceCommand:
        """只传 desired state；write_mode 始终由服务端维护规划器决定。"""

        return BoundaryMaintenanceCommand(
            expected_boundary_state_fingerprint=(
                self.expected_boundary_state_fingerprint
            ),
            actors=tuple(
                BoundaryMaintenanceActorItem.model_validate_json(_item_json(item))
                for item in self.actors
            ),
            actions=tuple(
                BoundaryMaintenanceActionItem.model_validate_json(_item_json(item))
                for item in self.actions
            ),
            permissions=tuple(
                BoundaryMaintenancePermissionItem.model_validate_json(
                    _item_json(item)
                )
                for item in self.permissions
            ),
            provenance=self.provenance,
        )


def build_business_boundaries_router(context: ApplicationCore) -> APIRouter:
    """构造唯一正式 Boundary API；Approve/Reject 身份始终由服务端固定。"""

    router = APIRouter()
    prefix = "/api/projects/{project_id}/business-boundaries"

    @router.get(prefix, response_model=ApiResponse)
    def get_boundary(project_id: str):
        return data_response(context.business_boundaries.view(project_id).model_dump(mode="json"))

    @router.get(f"{prefix}/preview", response_model=ApiResponse)
    def preview_boundary(project_id: str):
        return data_response(
            context.business_boundaries.preview_from_discovery(project_id).model_dump(mode="json")
        )

    @router.post(f"{prefix}/proposals", response_model=ApiResponse, status_code=201)
    def create_proposal(project_id: str, body: BoundaryProposalCreateRequest):
        return data_response(
            context.business_boundaries.create_initial_proposal(
                project_id,
                body.to_command(),
            ).model_dump(mode="json"),
            status_code=201,
        )

    @router.get(f"{prefix}/maintenance-draft", response_model=ApiResponse)
    def maintenance_draft(project_id: str):
        return data_response(
            context.business_boundaries.maintenance_draft(project_id).model_dump(
                mode="json"
            )
        )

    @router.post(
        f"{prefix}/maintenance-proposals",
        response_model=ApiResponse,
        status_code=201,
    )
    def create_maintenance_proposal(
        project_id: str,
        body: BoundaryMaintenanceCreateRequest,
    ):
        return data_response(
            context.business_boundaries.create_maintenance_proposal(
                project_id,
                body.to_command(),
            ).model_dump(mode="json"),
            status_code=201,
        )

    @router.get(f"{prefix}/proposals", response_model=ApiResponse)
    def list_proposals(project_id: str, pending_only: bool = False):
        return data_response(
            context.business_boundaries.proposals(
                project_id,
                pending_only=pending_only,
            ).model_dump(mode="json")
        )

    @router.get(f"{prefix}/proposals/{{proposal_id}}", response_model=ApiResponse)
    def get_proposal(project_id: str, proposal_id: str):
        return data_response(
            context.business_boundaries.proposal(project_id, proposal_id).model_dump(mode="json")
        )

    @router.post(f"{prefix}/proposals/{{proposal_id}}/approve", response_model=ApiResponse)
    def approve_proposal(project_id: str, proposal_id: str, body: BoundaryDecisionRequest):
        return data_response(
            context.business_boundaries.approve(
                project_id,
                proposal_id,
                expected_fingerprint=body.expected_fingerprint,
                reason=body.reason,
            ).model_dump(mode="json")
        )

    @router.post(f"{prefix}/proposals/{{proposal_id}}/reject", response_model=ApiResponse)
    def reject_proposal(project_id: str, proposal_id: str, body: BoundaryDecisionRequest):
        return data_response(
            context.business_boundaries.reject(
                project_id,
                proposal_id,
                expected_fingerprint=body.expected_fingerprint,
                reason=body.reason,
            ).model_dump(mode="json")
        )

    return router


__all__ = [
    "BoundaryDecisionRequest", "BoundaryMaintenanceCreateRequest",
    "BoundaryProposalCreateRequest", "build_business_boundaries_router",
]
