# 验证权限批准与检查准备请求不接受调用方伪造审批人。

import pytest
from pydantic import ValidationError

from product.backend.api.routers.checks import CheckPrepareRequest
from product.backend.api.routers.permission_intents import (
    PermissionIntentApprovalRequest,
    PermissionIntentProposalApprovalRequest,
    PermissionIntentProposalDecisionRequest,
)


def test_permission_requests_reject_arbitrary_actor_fields() -> None:
    with pytest.raises(ValidationError):
        PermissionIntentApprovalRequest.model_validate(
            {
                "schema_version": "1",
                "target": {
                    "action_candidate_id": "action_" + "1" * 32,
                    "subject_role_candidate_id": "role_" + "2" * 32,
                    "resource_owner_role_candidate_id": "role_" + "3" * 32,
                    "relation": "OWNS",
                },
                "expectation": "ALLOW",
                "actor": "伪造审批人",
            }
        )
    with pytest.raises(ValidationError):
        PermissionIntentProposalApprovalRequest.model_validate(
            {"schema_version": "1", "actor": "伪造审批人"}
        )
    with pytest.raises(ValidationError):
        PermissionIntentProposalDecisionRequest.model_validate(
            {"schema_version": "1", "actor": "伪造审批人"}
        )
    with pytest.raises(ValidationError):
        CheckPrepareRequest.model_validate(
            {"schema_version": "1", "actor": "伪造准备人"}
        )
