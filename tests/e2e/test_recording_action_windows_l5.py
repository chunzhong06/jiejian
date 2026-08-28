# Windows L5：真实测试身份录制 Sample 修改、独立观察和安全恢复动作。

from __future__ import annotations

import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from product.backend.core.application_understanding import (
    ActionCandidate,
    ActionRiskHint,
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
    candidate_id,
)
from product.backend.core.lifecycle import ProjectStatus
from product.backend.core.test_identity import TestIdentityCookie as IdentityCookie
from product.backend.infra.identity.browser import IdentityPreparationBrowserAdapter
from product.backend.infra.recording.browser import (
    BrowserRecordingAdapter,
    RecordingBrowserSession,
)
from product.backend.infra.secrets import WindowsCredentialManagerSecretStore
from product.backend.infra.storage import ProjectRecord
from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.recording.processing import FlowDraftProcessor
from product.backend.workflows.recording.review import FlowDraftReviewer
from product.backend.workflows.test_identities import PreparedLoginState
from product.protocols import (
    ConfirmFlowDraftResource,
    ConfirmFlowDraftTarget,
    ConfirmFlowDraftVariable,
    IdentityPreparationRequest,
    IdentityPreparationResultType,
    RecordingBudget,
    RecordingRunnerRequest,
    RecordingRunnerResultType,
    required_recording_secret_names,
)
from product.protocols.web.target import WebTargetScope
from product.protocols.web.workflow import (
    ValueSlotSource,
    WorkflowStepPurpose,
)


pytestmark = [
    pytest.mark.browser,
    pytest.mark.process,
    pytest.mark.slow,
    pytest.mark.skipif(
        os.name != "nt"
        or os.environ.get("JIEJIAN_RUN_RECORDING_WINDOWS_L5") != "1",
        reason="requires explicit action recording Windows L5 authorization",
    ),
]


def test_prepared_identity_records_web_action_observe_and_restore_without_profile(
    tmp_path: Path,
    web_test_target_factory,
    request: pytest.FixtureRequest,
) -> None:
    """闭合准备身份、TARGET、所有者读取、恢复读取与 Flow v5 编译。"""

    sample = web_test_target_factory()
    endpoint = f"http://127.0.0.1:{sample.port}"
    project_id = "web-test-project"
    role_id = candidate_id("role", "member")
    action_id = candidate_id("action", "modify-resource")
    var_dir = tmp_path / "var"
    store = WindowsCredentialManagerSecretStore()
    cleanup_refs: set[str] = set()

    def cleanup_credentials() -> None:
        for secret_ref in tuple(cleanup_refs):
            try:
                store.delete(secret_ref)
            except OSError:
                pass

    request.addfinalizer(cleanup_credentials)
    application = ApplicationCore(var_dir, secret_store=store, environ={})
    identity_id = ""
    recording_id = f"rec_{uuid4().hex}"
    try:
        with application.uow_factory() as work:
            work.projects.add(
                ProjectRecord(
                    project_id=project_id,
                    name="权限样例",
                    status=ProjectStatus.DRAFT,
                    created_at_us=1,
                    updated_at_us=1,
                )
            )
            work.application_understanding.add(
                ApplicationUnderstanding(
                    project_id=project_id,
                    source_root="D:/web-test",
                    confirmed_endpoint=endpoint,
                    endpoint_source_fingerprint="a" * 64,
                    endpoint_confirmed_at_us=2,
                    endpoint_last_checked_at_us=2,
                    endpoint_reachable=True,
                    role_candidates=(
                        RoleCandidate(
                            candidate_id=role_id,
                            canonical_key="member",
                            display_name="成员",
                            confidence=CandidateConfidence.HIGH,
                            decision=CandidateDecision.CONFIRMED,
                            origin=CandidateOrigin.MANUAL,
                        ),
                    ),
                    action_candidates=(
                        ActionCandidate(
                            candidate_id=action_id,
                            canonical_key="modify-resource",
                            display_name="修改资源",
                            confidence=CandidateConfidence.HIGH,
                            risk_hint=ActionRiskHint.WRITE,
                            decision=CandidateDecision.CONFIRMED,
                            origin=CandidateOrigin.MANUAL,
                        ),
                    ),
                    revision=3,
                    created_at_us=1,
                    updated_at_us=2,
                )
            )
            work.commit()
        identity = application.test_identities.create(
            project_id,
            role_candidate_id=role_id,
            label="所有者测试账号",
        )
        identity_id = identity.identity_id
        preparation = IdentityPreparationRequest(
            schema_version="1",
            preparation_id=f"prep_{uuid4().hex}",
            project_id=project_id,
            identity_id=identity_id,
            target_scope=_target_scope(endpoint, sample.port),
        )

        def login(page) -> None:
            page.select_option('select[name="role"]', "member")
            page.fill('input[name="password"]', sample.passwords["member"])
            page.click('button[type="submit"]')
            page.wait_for_load_state("domcontentloaded")
            page.goto(f"{endpoint}/resources/document")
            page.wait_for_load_state("domcontentloaded")

        preparation_result = IdentityPreparationBrowserAdapter().run(
            preparation,
            secret_store=store,
            ready_callback=lambda: None,
            save_requested=lambda: True,
            cancellation_requested=lambda: False,
            before_secret_write=lambda refs: cleanup_refs.update(refs),
            interaction=login,
        )
        assert preparation_result.result_type is IdentityPreparationResultType.PREPARED
        application.test_identities.save_prepared_state(
            identity_id,
            PreparedLoginState(
                auth_method=preparation_result.auth_method,
                cookies=tuple(
                    IdentityCookie(**cookie.model_dump())
                    for cookie in preparation_result.cookies
                ),
                prepared_at_us=preparation_result.prepared_at_us,
            ),
        )

        now_us = time.time_ns() // 1_000
        session = application.recording_credentials.prepare(
            project_id=project_id,
            test_identity_id=identity_id,
            recording_id=recording_id,
            session_ref=f"session_{uuid4().hex}",
            now_us=now_us,
            expires_at_us=now_us + 60_000_000,
        )
        recording_request = RecordingRunnerRequest(
            schema_version="1",
            recording_id=recording_id,
            project_id=project_id,
            action_candidate_id=action_id,
            created_at_us=now_us,
            target_scope=_target_scope(endpoint, sample.port),
            sessions=(session,),
            budget=RecordingBudget(
                max_duration_us=30_000_000,
                max_contexts=1,
            ),
            headless=False,
            trace_enabled=False,
        )
        secret_names = required_recording_secret_names(recording_request)
        environment = application.environment_for_secret_names(secret_names)
        secret_values = {name: environment[name] for name in secret_names}
        signals = {"start": False, "stop": False}
        observed: dict[str, object] = {}

        def record_modify(session: RecordingBrowserSession) -> None:
            page = session.new_page(identity_id)
            page.goto(f"{endpoint}/resources/document")
            signals["start"] = True
            assert session.wait_for_capture_start(page, identity_id)
            observed.update(
                page.evaluate(
                    """async (url) => {
                    const target = await fetch(url, {
                        method: 'PATCH',
                        credentials: 'include',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({value: 'recorded-member-value'})
                    });
                    const changed = await fetch(url, {credentials: 'include'});
                    const changedBody = await changed.json();
                    const cleanup = await fetch(url, {
                        method: 'PATCH',
                        credentials: 'include',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({value: 'initial-document-value'})
                    });
                    const restored = await fetch(url, {credentials: 'include'});
                    const restoredBody = await restored.json();
                    return {
                        target_status: target.status,
                        observation_status: changed.status,
                        observed_value: changedBody.value,
                        recovery_status: cleanup.status,
                        restored_status: restored.status,
                        restored_value: restoredBody.value,
                    };
                    }""",
                    f"{endpoint}/resources/document",
                )
            )
            page.wait_for_timeout(200)
            signals["stop"] = True
            assert session.stop_requested()

        recording_result = BrowserRecordingAdapter().run(
            recording_request,
            record_modify,
            known_secrets=tuple(secret_values.values()),
            secret_values=secret_values,
            capture_controlled=True,
            start_requested=lambda: signals["start"],
            stop_requested=lambda: signals["stop"],
        )
        assert recording_result.result_type is RecordingRunnerResultType.CAPTURED
        assert observed == {
            "target_status": 200,
            "observation_status": 200,
            "observed_value": "recorded-member-value",
            "recovery_status": 200,
            "restored_status": 200,
            "restored_value": "initial-document-value",
        }
        assert [
            event.method
            for event in recording_result.events
            if event.url == f"{endpoint}/resources/document"
            and event.method is not None
        ] == ["PATCH", "GET", "PATCH", "GET"]

        draft = FlowDraftProcessor().build(
            recording_id=recording_id,
            flow_id="web-test-modify-resource",
            action_candidate_id=action_id,
            events=recording_result.events,
            known_secrets=tuple(secret_values.values()),
        )
        assert draft.recommended_target_step_id is not None
        target_request_id = next(
            event.request_id
            for event in recording_result.events
            if event.method == "PATCH"
            and event.body is not None
            and "recorded-member-value" in event.body
        )
        target_step_id = next(
            step.id for step in draft.steps if step.request_id == target_request_id
        )
        reviewer = FlowDraftReviewer()
        # 真实响应是否形成动态变量取决于本次捕获内容；L5 必须走完公开审阅边界，
        # 不能依赖“恰好没有变量”才能编译。
        reviewed = draft
        for variable in draft.variables:
            source = variable.candidate_sources[0]
            reviewed = reviewer.apply(
                reviewed,
                ConfirmFlowDraftVariable(
                    schema_version="1",
                    operation="CONFIRM_VARIABLE_SOURCE",
                    variable_name=variable.name,
                    source_event_sequence=source.source_event_sequence,
                    source_json_path=source.json_path,
                ),
            )
        reviewed = reviewer.apply(
            reviewed,
            ConfirmFlowDraftTarget(
                schema_version="1",
                operation="CONFIRM_TARGET_STEP",
                step_id=target_step_id,
            ),
        )
        target = next(
            step for step in reviewed.steps if step.id == reviewed.target_step_id
        )
        resource = next(
            candidate
            for candidate in target.resource_candidates
            if candidate.location == "path[1]"
        )
        ready = reviewer.apply(
            reviewed,
            ConfirmFlowDraftResource(
                schema_version="1",
                operation="CONFIRM_RESOURCE_SLOT",
                candidate_id=resource.candidate_id,
            ),
        )
        flow = reviewer.compile(ready)

        assert flow.schema_version == "1"
        assert flow.action_candidate_id == action_id
        assert len(flow.steps) == 1
        assert flow.steps[0].purpose is WorkflowStepPurpose.TARGET
        assert flow.steps[0].request_template.method == "PATCH"
        assert flow.steps[0].request_template.path == "/resources/{case_resource_id}"
        assert any(
            slot.source is ValueSlotSource.CASE_RESOURCE_ID
            for slot in flow.steps[0].request_template.input_slots
        )
        assert "profile" not in recording_request.model_dump_json().casefold()
        assert "profile" not in flow.model_dump_json().casefold()
        with sample.server.lock:
            assert (
                sample.server.documents["document"]["value"]
                == "initial-document-value"
            )
    finally:
        application.recording_credentials.clear(recording_id)
        if identity_id:
            application.test_identities.delete(identity_id)
        application.close()


def _target_scope(endpoint: str, port: int) -> WebTargetScope:
    return WebTargetScope(
        base_url=endpoint,
        allowed_origins=(endpoint,),
        allowed_hosts=("127.0.0.1",),
        allowed_ports=(port,),
        allow_private_network=True,
        timeout_seconds=10.0,
        max_requests=64,
        max_response_bytes=262_144,
    )
