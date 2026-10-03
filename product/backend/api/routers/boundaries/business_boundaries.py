# Business Boundary 控制面 API：把 JSON DTO 转为严格领域命令。
# 不生成正式 ID、Approval 或 epoch；Approve/Reject 身份始终由服务端固定。

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.composition import ApplicationCore
from product.backend.core.boundaries.proposals import ProposedActionItem, ProposedActorItem, ProposedPermissionItem
from product.backend.core.boundaries.rule_candidates import RuleCandidateSave
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


class RuleCandidateSaveRequest(ApiModel):
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_basis_id: str = Field(pattern=r"^rb_[0-9a-f]{64}$")
    candidate_id: str | None = Field(default=None, pattern=r"^rcd_[0-9a-f]{32}$")
    expected_revision: int | None = Field(default=None, ge=1)
    content: dict[str, object]

    def to_command(self) -> RuleCandidateSave:
        return RuleCandidateSave.model_validate_json(self.model_dump_json())


class RuleCandidateProposalRequest(ApiModel):
    operation_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    revision: int = Field(ge=1)


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

    @router.get(f"{prefix}/rules/{{intent_id}}", response_model=ApiResponse)
    def rule_details(project_id: str, intent_id: str, revision: int | None = None):
        return data_response(context.rule_details.read(project_id,intent_id,revision=revision))

    @router.get(f"{prefix}/rule-context", response_model=ApiResponse)
    def rule_context(project_id: str, offset: int = 0):
        return data_response(jsonable_encoder(context.rule_candidates.context(project_id, offset=offset)))

    @router.post(f"{prefix}/rule-candidates", response_model=ApiResponse, status_code=201)
    def save_rule_candidate(project_id: str, body: RuleCandidateSaveRequest):
        return data_response(jsonable_encoder(context.rule_candidates.save(
            project_id, body.to_command(), submitted_via="LOCAL_GUI")), status_code=201)

    @router.get(f"{prefix}/rule-candidates/{{candidate_id}}", response_model=ApiResponse)
    def show_rule_candidate(project_id: str, candidate_id: str, revision: int | None = None):
        return data_response(jsonable_encoder(context.rule_candidates.show(project_id, candidate_id, revision)))

    @router.post(f"{prefix}/rule-candidates/{{candidate_id}}/proposals", response_model=ApiResponse, status_code=201)
    def propose_rule_candidate(project_id: str, candidate_id: str, body: RuleCandidateProposalRequest):
        return data_response(jsonable_encoder(context.rule_candidates.propose(project_id, candidate_id,
            revision=body.revision, operation_id=body.operation_id)), status_code=201)

    @router.get(f"{prefix}/rule-operations/{{kind}}/{{operation_id}}", response_model=ApiResponse)
    def rule_operation(project_id: str, kind: Literal["SAVE", "PROPOSE"], operation_id: str):
        return data_response(jsonable_encoder(context.rule_candidates.operation(project_id, kind, operation_id)))

    @router.get(prefix, response_model=ApiResponse)
    def get_boundary(project_id: str):
        return data_response(context.business_boundaries.view(project_id).model_dump(mode="json"))

    @router.get(f"{prefix}/preview", response_model=ApiResponse)
    def preview_boundary(project_id: str):
        return data_response(
            context.business_boundaries.preview_from_discovery(project_id).model_dump(mode="json")
        )

    @router.get(f"{prefix}/editor", response_model=ApiResponse)
    def editor_boundary(project_id: str):
        return data_response(context.business_boundaries.editor(project_id).model_dump(mode="json"))

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
