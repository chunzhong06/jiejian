# 验证权限意图只有 human-only HTTP 审批能形成 revision，Agent 建议只能等待审阅。

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from product.backend.api.routers.permission_intents import build_permission_intents_router
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentSemantic,
)
from product.backend.core.verification.permissions import PermissionExpectation
from tests.backend.workflows.recording.test_action_safety_setup import (
    ACTION_ID,
    PROJECT_ID,
    ROLE_ID,
)
from tests.backend.workflows.security_setup.test_checks import _prepared_core


def test_human_approval_replaces_old_cell_mutation_and_appends_history(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    app = FastAPI()
    app.include_router(build_permission_intents_router(core))
    try:
        before = core.permission_intents.matrix(PROJECT_ID)
        owns_before = next(
            cell
            for action in before.actions
            for cell in action.cells
            if cell.relation.value == "OWNS"
        )
        assert owns_before.protected_effects
        with TestClient(app) as client:
            removed = client.put(
                f"/api/projects/{PROJECT_ID}/permission-intents/{ACTION_ID}/"
                f"{ROLE_ID}/{ROLE_ID}/OWNS",
                json={"schema_version": "1", "expectation": "DENY"},
            )
            assert removed.status_code == 404

            approved = client.post(
                f"/api/projects/{PROJECT_ID}/permission-intents/approvals",
                json={
                    "schema_version": "1",
                    "target": {
                        "action_candidate_id": ACTION_ID,
                        "subject_role_candidate_id": ROLE_ID,
                        "resource_owner_role_candidate_id": ROLE_ID,
                        "relation": "OWNS",
                    },
                    "expectation": "DENY",
                    "reason": "用户确认该动作必须拒绝",
                },
            )
            assert approved.status_code == 200
            assert approved.json()["data"]["policy_epoch"] == before.policy_epoch + 1
            intent = next(
                item
                for item in core.permission_intents.current_intents(PROJECT_ID)
                if item.relation.value == "OWNS"
            )

            history = client.get(
                f"/api/projects/{PROJECT_ID}/permission-intents/{intent.intent_id}/history"
            )
            assert history.status_code == 200
            revisions = history.json()["data"]["revisions"]
            assert [item["revision"] for item in revisions] == [1, 2]
            assert revisions[-1]["approval"]["approved_by"] == "本机界鉴用户"
            assert revisions[-1]["approval"]["reason"] == "用户确认该动作必须拒绝"

            retired = client.post(
                f"/api/projects/{PROJECT_ID}/permission-intents/approvals",
                json={
                    "schema_version": "1",
                    "target": {
                        "action_candidate_id": ACTION_ID,
                        "subject_role_candidate_id": ROLE_ID,
                        "resource_owner_role_candidate_id": ROLE_ID,
                        "relation": "OWNS",
                    },
                    "expectation": None,
                },
            )
            assert retired.status_code == 200
            latest = core.permission_intents.history(PROJECT_ID, intent.intent_id).revisions[-1]
            assert latest.revision == 3
            assert latest.effective_state is PermissionIntentEffectiveState.RETIRED
            assert retired.json()["data"]["policy_epoch"] == before.policy_epoch + 2
    finally:
        core.close()


def test_agent_proposal_requires_explicit_human_approval_or_rejection(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    app = FastAPI()
    app.include_router(build_permission_intents_router(core))
    try:
        owns = next(
            item
            for item in core.permission_intents.current_intents(PROJECT_ID)
            if item.relation.value == "OWNS"
        )
        before = core.permission_intents.matrix(PROJECT_ID)
        proposed = core.permission_intents.propose_semantic_change(
            PROJECT_ID,
            PermissionIntentSemantic(
                effective_state=PermissionIntentEffectiveState.ACTIVE,
                subject_display_name=owns.subject_display_name,
                action_display_name=owns.action_display_name,
                resource_owner_display_name=owns.resource_owner_display_name,
                relation=owns.relation,
                expectation=PermissionExpectation.DENY,
                protected_effects=owns.protected_effects,
            ),
            proposed_by="MCP Agent",
            reason="建议把所有者本人修改改为拒绝",
            intent_id=owns.intent_id,
        )
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == before.policy_epoch

        with TestClient(app) as client:
            listed = client.get(
                f"/api/projects/{PROJECT_ID}/permission-intent-proposals"
            )
            assert listed.status_code == 200
            assert [item["proposal_id"] for item in listed.json()["data"]["proposals"]] == [
                proposed.proposal_id
            ]

            approved = client.post(
                f"/api/projects/{PROJECT_ID}/permission-intent-proposals/"
                f"{proposed.proposal_id}/approve",
                json={"schema_version": "1", "reason": "用户接受收紧建议"},
            )
            assert approved.status_code == 200
            assert approved.json()["data"]["status"] == "APPROVED"
            changed = core.permission_intents.matrix(PROJECT_ID)
            assert changed.policy_epoch == before.policy_epoch + 1
            assert core.permission_intents.history(PROJECT_ID, owns.intent_id).revisions[-1].expectation is PermissionExpectation.DENY

            rejectable = core.permission_intents.propose_semantic_change(
                PROJECT_ID,
                PermissionIntentSemantic(
                    effective_state=PermissionIntentEffectiveState.ACTIVE,
                    subject_display_name=owns.subject_display_name,
                    action_display_name=owns.action_display_name,
                    resource_owner_display_name=owns.resource_owner_display_name,
                    relation=owns.relation,
                    expectation=PermissionExpectation.ALLOW,
                    protected_effects=owns.protected_effects,
                ),
                proposed_by="MCP Agent",
                reason="建议重新允许所有者本人修改",
                intent_id=owns.intent_id,
            )
            rejected = client.post(
                f"/api/projects/{PROJECT_ID}/permission-intent-proposals/"
                f"{rejectable.proposal_id}/reject",
                json={"schema_version": "1"},
            )
            assert rejected.status_code == 200
            assert rejected.json()["data"]["status"] == "REJECTED"
            assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == changed.policy_epoch
            assert client.get(
                f"/api/projects/{PROJECT_ID}/permission-intent-proposals"
            ).json()["data"]["proposals"] == []
    finally:
        core.close()


def test_permission_draft_api_is_explicit_non_activating_and_schema_bounded(
    tmp_path: Path,
) -> None:
    core = _prepared_core(tmp_path)
    app = FastAPI()
    app.include_router(build_permission_intents_router(core))
    try:
        before = core.permission_intents.matrix(PROJECT_ID)
        before_intents = tuple(
            (item.intent_id, item.revision, item.intent_hash)
            for item in core.permission_intents.current_intents(PROJECT_ID)
        )
        with TestClient(app) as client:
            drafted = client.post(
                f"/api/projects/{PROJECT_ID}/permission-drafts",
                json={
                    "schema_version": "1",
                    "text": "所有者可以修改自己的资源。",
                },
            )
            invalid = client.post(
                f"/api/projects/{PROJECT_ID}/permission-drafts",
                json={"schema_version": "1", "text": "越界字段", "apply": True},
            )
            assert client.post(
                f"/api/projects/{PROJECT_ID}/permission-drafts/apply",
                json={"schema_version": "1"},
            ).status_code == 404

        after = core.permission_intents.matrix(PROJECT_ID)
        assert drafted.status_code == 200
        assert drafted.json()["data"]["status"] == "UNAVAILABLE"
        assert invalid.status_code == 422
        assert after.policy_epoch == before.policy_epoch
        assert tuple(
            (item.intent_id, item.revision, item.intent_hash)
            for item in core.permission_intents.current_intents(PROJECT_ID)
        ) == before_intents
    finally:
        core.close()
