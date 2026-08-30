# 项目式录制提交测试：验证有界输入与同动作、同账号补录关系。

from types import SimpleNamespace

import pytest

from product.backend.core.application_understanding import (
    ActionCandidate,
    CandidateConfidence,
    CandidateDecision,
    CandidateOrigin,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.recording import RecordingPurpose, RecordingState
from product.backend.workflows.recording.project_submission import ProjectRecordingService
from product.protocols import RecordingAuthMethod, RecordingSessionRef


ACTION_ID = "action_" + "1" * 32
IDENTITY_ID = "tid_" + "2" * 32
PARENT_ID = "rec_" + "3" * 32


class _Work:
    def __init__(self, parent, job) -> None:
        self.recordings = SimpleNamespace(get=lambda _recording_id: parent)
        self.jobs = SimpleNamespace(get_by_recording=lambda _recording_id: job)

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


def _supplement_service(*, parent_action_id: str = ACTION_ID):
    parent = SimpleNamespace(
        project_id="project_current",
        purpose=RecordingPurpose.TARGET,
        state=RecordingState.COMPLETED,
    )
    job = SimpleNamespace(job_id="job_" + "4" * 32, request_hash="a" * 64)
    parent_request = SimpleNamespace(
        action_candidate_id=parent_action_id,
        sessions=(SimpleNamespace(test_identity_id=IDENTITY_ID),),
    )
    action = ActionCandidate(
        candidate_id=ACTION_ID,
        canonical_key="modify-resource",
        display_name="修改资源",
        confidence=CandidateConfidence.HIGH,
        decision=CandidateDecision.CONFIRMED,
        origin=CandidateOrigin.MANUAL,
    )
    captured: list[object] = []
    submission = SimpleNamespace(
        submit=lambda command: captured.append(command) or SimpleNamespace()
    )
    service = ProjectRecordingService(
        SimpleNamespace(
            get=lambda _project_id: SimpleNamespace(
                action_candidates=(action,),
                confirmed_endpoint="http://127.0.0.1:8865",
            )
        ),
        SimpleNamespace(get=lambda _identity_id: SimpleNamespace(label="普通成员账号")),
        SimpleNamespace(
            prepare=lambda **_kwargs: RecordingSessionRef(
                test_identity_id=IDENTITY_ID,
                session_ref="session_" + "5" * 32,
                auth_method=RecordingAuthMethod.BEARER,
                bearer_ref="env:RECORDING_BEARER",
                expires_at_us=61_000_000,
            ),
            clear=lambda _recording_id: None,
        ),
        submission,
        uow_factory=lambda: _Work(parent, job),
        request_store=SimpleNamespace(load=lambda *_args, **_kwargs: parent_request),
        clock_us=lambda: 1_000_000,
    )
    return service, captured


def test_project_recording_rejects_unbounded_duration_before_side_effects() -> None:
    service = ProjectRecordingService(None, None, None, None)

    with pytest.raises(JiejianError) as captured:
        service.submit(
            "project_current",
            action_candidate_id="action_current",
            test_identity_id="tid_current",
            duration_seconds=0,
            idempotency_key="recording-current",
        )

    assert captured.value.code == ErrorCode.INPUT_INVALID.value


def test_supplement_reuses_parent_action_and_identity() -> None:
    service, captured = _supplement_service()

    result = service.submit(
        "project_current",
        action_candidate_id=ACTION_ID,
        test_identity_id=IDENTITY_ID,
        duration_seconds=60,
        idempotency_key="supplement-observation",
        purpose=RecordingPurpose.OBSERVATION,
        parent_recording_id=PARENT_ID,
    )

    assert result.request.action_candidate_id == ACTION_ID
    assert result.request.sessions[0].test_identity_id == IDENTITY_ID
    assert captured[0].purpose is RecordingPurpose.OBSERVATION
    assert captured[0].parent_recording_id == PARENT_ID


def test_supplement_rejects_different_parent_action_before_browser_session() -> None:
    service, captured = _supplement_service(parent_action_id="action_" + "9" * 32)

    with pytest.raises(JiejianError) as error:
        service.submit(
            "project_current",
            action_candidate_id=ACTION_ID,
            test_identity_id=IDENTITY_ID,
            duration_seconds=60,
            idempotency_key="supplement-mismatch",
            purpose=RecordingPurpose.RECOVERY,
            parent_recording_id=PARENT_ID,
        )

    assert error.value.code == ErrorCode.INPUT_INVALID.value
    assert captured == []
