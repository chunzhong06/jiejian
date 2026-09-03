# 验证 MCP 的 READ/PREPARE/EXECUTE 工具不能改变人类权限真源，只有 Human Approval 可以推进版本。

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import anyio
import httpx2
import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client
from pydantic import BaseModel

from product.backend.api.mcp import build_mcp_control
from product.backend.core.errors import JiejianError
from product.backend.core.permission_intent import IntentImplementationBindingStatus
from product.backend.core.source_changes import SourceFileFingerprint, source_fingerprint
from product.backend.infra.runtime.jobs.requests import ExecutionRequestStore
from product.backend.workflows.application_understanding.analysis.models import (
    ApplicationAnalysisResult,
)
from product.backend.workflows.mcp_access import MCPAccessController, MCPAccessLevel
from tests.backend.api.test_mcp import EXPECTED_MCP_TOOLS, _MemorySecretStore
from tests.backend.workflows.recording.test_action_safety_setup import (
    ACTION_ID,
    IDENTITY_ID,
    NOW_US,
    PROJECT_ID,
    ROLE_ID,
)
from tests.backend.workflows.security_setup.test_checks import _prepared_core


pytestmark = pytest.mark.database
CONTROL_ORIGIN = "http://127.0.0.1:8765"


class _ToolRecord(BaseModel):
    job_id: str


class _PreparationView(BaseModel):
    preparation_id: str
    identity_id: str
    state: str
    log_path: str


class _RecordingView(BaseModel):
    recording_id: str
    project_id: str
    flow_id: str
    state: str
    created_at_us: int
    updated_at_us: int


class _StaticAnalyzer:
    def __init__(self, result: ApplicationAnalysisResult) -> None:
        self._result = result

    def analyze(self, _project_id: str, _source_root: str) -> ApplicationAnalysisResult:
        return self._result


def test_official_mcp_execute_cannot_change_permission_oracle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core = _prepared_core(tmp_path)
    store = _MemorySecretStore()
    access = MCPAccessController(f"{CONTROL_ORIGIN}/mcp", store)
    control = build_mcp_control(
        core,
        access,
        control_origin=CONTROL_ORIGIN,
        control_host="127.0.0.1:8765",
    )
    token = access.pair().access_token
    assert token is not None
    access.set_level(PROJECT_ID, MCPAccessLevel.EXECUTE)

    owns = next(
        item
        for item in core.permission_intents.current_intents(PROJECT_ID)
        if item.relation.value == "OWNS"
    )
    before_matrix = core.permission_intents.matrix(PROJECT_ID)
    before_policy = core.permission_intents.policy_snapshot(PROJECT_ID)
    with core.uow_factory() as work:
        revisions_before = work.permission_intents.list_revisions(PROJECT_ID)

    preparation = _PreparationView(
        preparation_id="prep-oracle",
        identity_id=IDENTITY_ID,
        state="READY",
        log_path="never-returned.log",
    )
    monkeypatch.setattr(core.identity_preparations, "start", lambda _identity_id: preparation)
    monkeypatch.setattr(core.identity_preparations, "status", lambda _preparation_id: preparation)
    monkeypatch.setattr(core.identity_preparations, "confirm", lambda _preparation_id: preparation)
    monkeypatch.setattr(core.identity_preparations, "cancel", lambda _preparation_id: preparation)

    recording = _RecordingView(
        recording_id="rec-oracle",
        project_id=PROJECT_ID,
        flow_id="flow-oracle",
        state="RECORDING",
        created_at_us=1,
        updated_at_us=2,
    )
    recording_status = SimpleNamespace(
        recording=recording,
        capture_phase="RECORDING",
        draft=None,
    )
    monkeypatch.setattr(
        core.project_recordings,
        "submit",
        lambda *_args, **_kwargs: SimpleNamespace(
            result=SimpleNamespace(
                job=_ToolRecord(job_id="job-recording-oracle"),
                recording=recording,
            ),
            action=SimpleNamespace(candidate_id=ACTION_ID),
            test_identity=SimpleNamespace(identity_id=IDENTITY_ID),
        ),
    )
    monkeypatch.setattr(core.recording_lifecycle, "status", lambda _recording_id: recording_status)
    monkeypatch.setattr(
        core.recording_lifecycle,
        "start_capture",
        lambda _recording_id: recording_status,
    )
    monkeypatch.setattr(
        core.recording_lifecycle,
        "stop_capture",
        lambda _recording_id: recording_status,
    )
    monkeypatch.setattr(
        "product.backend.api.mcp.time.time_ns",
        lambda: (NOW_US + 200) * 1_000,
    )

    current_understanding = core.application_understanding.get(PROJECT_ID)
    source_files = (
        SourceFileFingerprint(
            relative_path="app.py",
            content_sha256="e" * 64,
        ),
    )
    core.application_understanding.analyzer = _StaticAnalyzer(
        ApplicationAnalysisResult(
            source_fingerprint=source_fingerprint(source_files),
            files=source_files,
            role_candidates=current_understanding.role_candidates,
            action_candidates=current_understanding.action_candidates,
            files_read=1,
            total_bytes=1,
        )
    )
    captured: dict[str, str] = {}

    async def scenario() -> None:
        async with control.server.session_manager.run():
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=control.app),
                base_url=CONTROL_ORIGIN,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Origin": CONTROL_ORIGIN,
                },
                follow_redirects=True,
            ) as http_client:
                async with Client(
                    streamable_http_client(
                        f"{CONTROL_ORIGIN}/mcp",
                        http_client=http_client,
                        terminate_on_close=False,
                    )
                ) as client:
                    tool_names = {item.name for item in (await client.list_tools()).tools}
                    assert tool_names == EXPECTED_MCP_TOOLS
                    assert not any(
                        word in name
                        for name in tool_names
                        for word in ("permission_set", "candidate_decide", "approve", "reject")
                    )

                    listed = await client.call_tool(
                        "jiejian_intent_list",
                        {"project_id": PROJECT_ID},
                    )
                    assert listed.structured_content["policy_epoch"] == before_matrix.policy_epoch
                    shown = await client.call_tool(
                        "jiejian_intent_show",
                        {"project_id": PROJECT_ID, "intent_id": owns.intent_id},
                    )
                    assert shown.structured_content["revisions"][-1]["intent_hash"] == owns.intent_hash

                    proposal = await client.call_tool(
                        "jiejian_intent_propose",
                        {
                            "project_id": PROJECT_ID,
                            "intent_id": owns.intent_id,
                            "semantic": {
                                "effective_state": "ACTIVE",
                                "subject_display_name": owns.subject_display_name,
                                "action_display_name": owns.action_display_name,
                                "resource_owner_display_name": owns.resource_owner_display_name,
                                "relation": owns.relation.value,
                                "expectation": "DENY",
                                "protected_effects": [
                                    item.model_dump(mode="json")
                                    for item in owns.protected_effects
                                ],
                            },
                            "reason": "Agent 建议收紧所有者本人权限",
                        },
                    )
                    captured["semantic_proposal_id"] = proposal.structured_content[
                        "proposal_id"
                    ]
                    assert proposal.structured_content["status"] == "PENDING"
                    assert proposal.structured_content["proposed_by"] == "MCP Agent"

                    rebind = await client.call_tool(
                        "jiejian_intent_rebind_propose",
                        {
                            "project_id": PROJECT_ID,
                            "intent_id": owns.intent_id,
                            "action_candidate_id": ACTION_ID,
                            "subject_role_candidate_id": ROLE_ID,
                            "resource_owner_role_candidate_id": ROLE_ID,
                            "reason": "Agent 建议刷新当前实现映射",
                        },
                    )
                    captured["rebind_proposal_id"] = rebind.structured_content[
                        "proposal_id"
                    ]

                    prepared = await client.call_tool(
                        "jiejian_check_prepare",
                        {"project_id": PROJECT_ID},
                    )
                    assert prepared.is_error is False
                    for tool_name, arguments in (
                        (
                            "jiejian_identity_prepare_start",
                            {"project_id": PROJECT_ID, "identity_id": IDENTITY_ID},
                        ),
                        (
                            "jiejian_identity_prepare_confirm",
                            {"project_id": PROJECT_ID, "preparation_id": "prep-oracle"},
                        ),
                        (
                            "jiejian_identity_prepare_cancel",
                            {"project_id": PROJECT_ID, "preparation_id": "prep-oracle"},
                        ),
                        (
                            "jiejian_recording_start",
                            {
                                "project_id": PROJECT_ID,
                                "action_candidate_id": ACTION_ID,
                                "test_identity_id": IDENTITY_ID,
                                "duration_seconds": 30,
                                "idempotency_key": "oracle-recording",
                            },
                        ),
                        (
                            "jiejian_recording_capture_start",
                            {"project_id": PROJECT_ID, "recording_id": "rec-oracle"},
                        ),
                        (
                            "jiejian_recording_stop",
                            {"project_id": PROJECT_ID, "recording_id": "rec-oracle"},
                        ),
                    ):
                        assert (await client.call_tool(tool_name, arguments)).is_error is False

                    submitted = await client.call_tool(
                        "jiejian_check_run",
                        {
                            "project_id": PROJECT_ID,
                            "idempotency_key": "oracle-run",
                        },
                    )
                    captured["job_id"] = submitted.structured_content["job"]["job_id"]
                    cancelled = await client.call_tool(
                        "jiejian_check_cancel",
                        {"project_id": PROJECT_ID, "job_id": captured["job_id"]},
                    )
                    assert cancelled.is_error is False

                    reanalyzed = await client.call_tool(
                        "jiejian_application_reanalyze",
                        {
                            "project_id": PROJECT_ID,
                            "revision": current_understanding.revision,
                        },
                    )
                    assert reanalyzed.structured_content["revision"] == current_understanding.revision + 1
                    change = await client.call_tool(
                        "jiejian_change_submit",
                        {
                            "project_id": PROJECT_ID,
                            "reason": "Agent 完成实现调整",
                            "claimed_paths": ["untrusted-claim.py"],
                        },
                    )
                    captured["change_id"] = change.structured_content["change_id"]
                    shown_change = await client.call_tool(
                        "jiejian_change_show",
                        {
                            "project_id": PROJECT_ID,
                            "change_id": captured["change_id"],
                        },
                    )
                    assert shown_change.structured_content == change.structured_content
                    assert "source_fingerprint" not in shown_change.structured_content
                    assert "changed_paths" not in shown_change.structured_content

    try:
        anyio.run(scenario)

        with core.uow_factory() as work:
            assert work.permission_intents.list_revisions(PROJECT_ID) == revisions_before
            job = work.jobs.get(captured["job_id"])
            binding = work.permission_intents.binding(owns.intent_id, owns.revision)
        assert job is not None
        assert binding is not None
        assert binding.status is IntentImplementationBindingStatus.CURRENT
        assert core.permission_intents.matrix(PROJECT_ID).policy_epoch == before_matrix.policy_epoch
        frozen = ExecutionRequestStore(tmp_path / "var").load(
            job.job_id,
            expected_hash=job.request_hash,
        )
        assert frozen.permission_policy == before_policy

        with pytest.raises(JiejianError):
            core.permission_intents.approve_proposal(
                PROJECT_ID,
                captured["rebind_proposal_id"],
            )
        approved = core.permission_intents.approve_proposal(
            PROJECT_ID,
            captured["semantic_proposal_id"],
        )
        assert approved.status.value == "APPROVED"
        after_matrix = core.permission_intents.matrix(PROJECT_ID)
        latest = core.permission_intents.history(PROJECT_ID, owns.intent_id).revisions[-1]
        assert after_matrix.policy_epoch == before_policy.policy_epoch + 1
        assert latest.revision == owns.revision + 1
        assert latest.intent_hash != owns.intent_hash
    finally:
        access.close()
        core.close()
