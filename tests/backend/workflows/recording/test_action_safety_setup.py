# 验证录制候选只在用户确认后形成资源、独立观察与安全恢复事实。

from __future__ import annotations

import hashlib
from itertools import pairwise
from pathlib import Path

import pytest

from product.backend.core.application_understanding import (
    ActionCandidate,
    ActionRiskHint,
    ApplicationUnderstanding,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
    RoleCandidate,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import JobState, ProjectStatus
from product.backend.core.recording import Recording, RecordingState, RecordingStateEvent
from product.backend.core.test_identity import TestIdentity, TestIdentityAuthMethod
from product.backend.infra.storage import (
    FlowDraftRevisionRecord,
    JobRecord,
    ProjectRecord,
    RecordingRecord,
)
from product.backend.composition import ApplicationCore
from product.backend.workflows.recording.lifecycle import RecordingLifecycle
from product.backend.workflows.recording.processing import FlowDraftProcessor
from product.backend.workflows.recording.review import FlowDraftReviewer
from product.backend.workflows.recording.safety_setup import ConfirmActionSafetySetup
from product.backend.workflows.recording.safety_candidates import (
    _dedupe_candidates,
    _observation_key,
)
from product.protocols import (
    ConfirmFlowDraftResource,
    ConfirmFlowDraftTarget,
    RecordingAuthMethod,
    RecordingBudget,
    RecordingEvent,
    RecordingEventKind,
    RecordingRunnerRequest,
    RecordingSessionRef,
    canonical_flow_draft_json_bytes,
)
from product.protocols.web.target import WebTargetScope

pytestmark = pytest.mark.database

PROJECT_ID = "safety-project"
RECORDING_ID = "rec_" + "1" * 32
JOB_ID = "job_" + "2" * 32
IDENTITY_ID = "tid_" + "3" * 32
ROLE_ID = "role_" + "4" * 32
ACTION_ID = "action_" + "5" * 32
SOURCE_FINGERPRINT = "a" * 64
ENDPOINT_FINGERPRINT = "b" * 64
NOW_US = 1_830_000_000_000_000


class _FakeSecretStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def configured(self, secret_ref: str) -> bool:
        return secret_ref in self.values

    def read(self, secret_ref: str) -> str:
        return self.values[secret_ref]

    def write(self, secret_ref: str, value: str) -> None:
        self.values[secret_ref] = value

    def delete(self, secret_ref: str) -> None:
        self.values.pop(secret_ref, None)


def test_state_change_requires_confirmed_recovery_before_automatic_execution(
    tmp_path: Path,
) -> None:
    store = _FakeSecretStore()
    secret_ref = f"cred:jiejian/test-identity/{PROJECT_ID}/{IDENTITY_ID}/bearer"
    store.write(secret_ref, "opaque-test-state")
    core = ApplicationCore(
        tmp_path / "var",
        secret_store=store,
        clock_us=lambda: NOW_US + 100,
    )
    try:
        _persist_completed_recording(core, secret_ref)
        preview = core.action_safety_setup.preview(RECORDING_ID)
        assert len(preview.observation_candidates) == 1
        assert "录制步骤" not in preview.observation_candidates[0].label
        assert len(_dedupe_candidates(
            (preview.observation_candidates[0], preview.observation_candidates[0]),
            key=_observation_key,
        )) == 1

        complete = core.action_safety_setup.confirm(
            RECORDING_ID,
            _confirmation(preview),
        )
        assert complete.gaps == ()
        assert complete.automatic_execution_allowed is True
        assert complete.confirmed_setup is not None
        assert complete.confirmed_setup.resource.actual_resource_id == "owner-resource"
        assert complete.confirmed_setup.recovery is not None
        assert complete.confirmed_setup.recovery.path_template == (
            "/resources/{case_resource_id}"
        )
        assert complete.confirmed_setup.recovery.json_body_template == {
            "value": "original"
        }
    finally:
        core.close()


def _confirmation(
    preview,
    *,
    include_recovery: bool = False,
) -> ConfirmActionSafetySetup:
    return ConfirmActionSafetySetup(
        resource_candidate_id=preview.resource_candidates[0].candidate_id,
        logical_name="所有者的测试文档",
        resource_type="文档",
        observation_candidate_id=preview.observation_candidates[0].candidate_id,
        recovery_candidate_id=(
            preview.recovery_candidates[0].candidate_id if include_recovery else None
        ),
    )


def _persist_completed_recording(core: ApplicationCore, secret_ref: str) -> None:
    events = _recording_events()
    draft = FlowDraftProcessor().build(
        recording_id=RECORDING_ID,
        flow_id="modify-owner-resource",
        action_candidate_id=ACTION_ID,
        events=events,
    )
    reviewer = FlowDraftReviewer()
    targeted = reviewer.apply(
        draft,
        ConfirmFlowDraftTarget(
            schema_version="1",
            operation="CONFIRM_TARGET_STEP",
            step_id=draft.steps[0].id,
        ),
    )
    resource_candidate = next(
        item
        for item in targeted.steps[0].resource_candidates
        if item.location == "path[1]"
    )
    confirmed = reviewer.apply(
        targeted,
        ConfirmFlowDraftResource(
            schema_version="1",
            operation="CONFIRM_RESOURCE_SLOT",
            candidate_id=resource_candidate.candidate_id,
        ),
    )
    request = RecordingRunnerRequest(
        schema_version="1",
        recording_id=RECORDING_ID,
        project_id=PROJECT_ID,
        action_candidate_id=ACTION_ID,
        created_at_us=NOW_US,
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:18080",
            allowed_origins=("http://127.0.0.1:18080",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(18080,),
            allow_private_network=True,
        ),
        sessions=(
            RecordingSessionRef(
                test_identity_id=IDENTITY_ID,
                session_ref="session_" + "6" * 32,
                auth_method=RecordingAuthMethod.BEARER,
                bearer_ref="env:RECORDING_BEARER",
                expires_at_us=NOW_US + 1_000_000,
            ),
        ),
        budget=RecordingBudget(max_duration_us=1_000_000, max_contexts=1),
        headless=False,
        trace_enabled=False,
    )
    request_hash, _ = core.recording_request_store.write(JOB_ID, request)
    recording = Recording(
        recording_id=RECORDING_ID,
        project_id=PROJECT_ID,
        state=RecordingState.PENDING_REVIEW,
        created_at_us=NOW_US,
        updated_at_us=NOW_US + 6,
        started_at_us=NOW_US + 2,
        capture_finished_at_us=NOW_US + 5,
        events=_recording_state_events(),
    )
    with core.uow_factory() as work:
        work.projects.add(
            ProjectRecord(
                project_id=PROJECT_ID,
                name="安全准备测试",
                status=ProjectStatus.DRAFT,
                created_at_us=NOW_US,
                updated_at_us=NOW_US,
            )
        )
        work.application_understanding.add(_understanding())
        work.test_identities.add(
            TestIdentity(
                identity_id=IDENTITY_ID,
                project_id=PROJECT_ID,
                role_candidate_id=ROLE_ID,
                role_canonical_key="owner",
                role_display_name="所有者",
                label="所有者测试账号",
                confirmed_endpoint="http://127.0.0.1:18080",
                endpoint_source_fingerprint=ENDPOINT_FINGERPRINT,
                understanding_revision=3,
                auth_method=TestIdentityAuthMethod.BEARER,
                bearer_secret_ref=secret_ref,
                prepared_at_us=NOW_US + 1,
                refreshed_at_us=NOW_US + 1,
                created_at_us=NOW_US,
                updated_at_us=NOW_US + 1,
            )
        )
        work.recordings.add(
            RecordingRecord.from_domain(
                recording,
                flow_id="modify-owner-resource",
                browser_events=events,
            )
        )
        encoded = canonical_flow_draft_json_bytes(confirmed)
        work.flow_drafts.add(
            FlowDraftRevisionRecord(
                recording_id=RECORDING_ID,
                revision=confirmed.revision,
                flow_id=confirmed.flow_id,
                draft=confirmed,
                draft_sha256=hashlib.sha256(encoded).hexdigest(),
                created_at_us=NOW_US + 6,
            )
        )
        work.jobs.add(
            JobRecord(
                job_id=JOB_ID,
                project_id=PROJECT_ID,
                recording_id=RECORDING_ID,
                operation_type="BROWSER_RECORDING",
                state=JobState.SUCCEEDED,
                idempotency_key="safety-setup-recording",
                request_hash=request_hash,
                attempt=0,
                max_attempts=1,
                available_at_us=NOW_US,
                fencing_token=0,
                created_at_us=NOW_US,
                updated_at_us=NOW_US + 6,
            )
        )
        work.commit()
    RecordingLifecycle(core.uow_factory, var_dir=core.var_dir).finalize(
        RECORDING_ID,
        var_dir=core.var_dir,
        now_us=NOW_US + 7,
    )


def _understanding() -> ApplicationUnderstanding:
    return ApplicationUnderstanding(
        project_id=PROJECT_ID,
        source_root="D:/sample",
        confirmed_endpoint="http://127.0.0.1:18080",
        endpoint_source_fingerprint=ENDPOINT_FINGERPRINT,
        endpoint_confirmed_at_us=NOW_US,
        endpoint_last_checked_at_us=NOW_US,
        endpoint_reachable=True,
        source_analysis_authorized=True,
        source_analysis_authorized_at_us=NOW_US,
        source_fingerprint=SOURCE_FINGERPRINT,
        analysis_completed_at_us=NOW_US,
        role_candidates=(
            RoleCandidate(
                candidate_id=ROLE_ID,
                canonical_key="owner",
                display_name="所有者",
                confidence=CandidateConfidence.HIGH,
                decision=CandidateDecision.CONFIRMED,
                origin=CandidateOrigin.MANUAL,
            ),
        ),
        action_candidates=(
            ActionCandidate(
                candidate_id=ACTION_ID,
                canonical_key="modify_owner_resource",
                display_name="修改所有者资源",
                confidence=CandidateConfidence.HIGH,
                risk_hint=ActionRiskHint.WRITE,
                decision=CandidateDecision.CONFIRMED,
                origin=CandidateOrigin.MANUAL,
            ),
        ),
        revision=3,
        created_at_us=NOW_US,
        updated_at_us=NOW_US,
    )


def _recording_state_events() -> tuple[RecordingStateEvent, ...]:
    states = (
        RecordingState.CREATED,
        RecordingState.STARTING,
        RecordingState.RECORDING,
        RecordingState.CLEANING,
        RecordingState.PROCESSING,
        RecordingState.PENDING_REVIEW,
    )
    return tuple(
        RecordingStateEvent(
            sequence=index,
            source=source,
            target=target,
            operator="TEST_SETUP",
            occurred_at_us=NOW_US + index + 1,
        )
        for index, (source, target) in enumerate(pairwise(states), start=1)
    )


def _recording_events() -> tuple[RecordingEvent, ...]:
    requests = (
        ("PATCH", "request_000001", '{"value":"changed"}'),
        ("GET", "request_000002", None),
        ("PATCH", "request_000003", '{"value":"original"}'),
        ("GET", "request_000004", None),
    )
    events: list[RecordingEvent] = []
    sequence = 1
    for method, request_id, body in requests:
        events.append(
            RecordingEvent(
                sequence=sequence,
                occurred_at_us=NOW_US + 10 + sequence,
                kind=RecordingEventKind.REQUEST,
                identity_id="recording-owner",
                page_id="page_000001",
                frame_id="frame_000001",
                request_id=request_id,
                url="http://127.0.0.1:18080/resources/owner-resource",
                method=method,
                resource_type="fetch",
                body=body,
            )
        )
        sequence += 1
        events.append(
            RecordingEvent(
                sequence=sequence,
                occurred_at_us=NOW_US + 10 + sequence,
                kind=RecordingEventKind.RESPONSE,
                identity_id="recording-owner",
                page_id="page_000001",
                frame_id="frame_000001",
                request_id=request_id,
                url="http://127.0.0.1:18080/resources/owner-resource",
                status_code=200,
                body=(
                    '{"state":"changed"}'
                    if request_id == "request_000002"
                    else '{"state":"original"}'
                    if request_id == "request_000004"
                    else "{}"
                ),
            )
        )
        sequence += 1
    return tuple(events)
