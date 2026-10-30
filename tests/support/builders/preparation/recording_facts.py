# 构造不依赖数据库或浏览器的冻结录制请求与结果事实。
from __future__ import annotations
from product.backend.domain.recording.models import RecordingState, RecordingStateEvent
from product.protocols.recording.events import (
    RecordingCleanupStatus,
    RecordingEvent,
    RecordingHeader,
    RecordingRunnerResult,
)
from product.protocols.web.target import WebTargetScope
from product.protocols.recording.events import (
    RecordingAuthMethod,
    RecordingBudget,
    RecordingEventKind,
    RecordingRunnerRequest,
    RecordingRunnerResultType,
    RecordingSessionRef,
)


NOW_US = 1_820_000_000_000_000


PROJECT_ID = "recording-project"


TEST_IDENTITY_ID = "tid_0123456789abcdef0123456789abcdef"


def runner_request(
    recording_id: str,
    *,
    secret_refs: tuple[str, ...] = ("env:RECORDING_SECRET",),
) -> RecordingRunnerRequest:
    return RecordingRunnerRequest(
        schema_version="3",
        recording_id=recording_id,
        project_id=PROJECT_ID,
        business_action_id="bac_" + "1" * 32,
        action_revision=1,
        subject_test_identity_id=TEST_IDENTITY_ID,
        resource_owner_test_identity_id=TEST_IDENTITY_ID,
        subject_slot_id="isl_" + "1" * 32,
        resource_owner_slot_id="isl_" + "1" * 32,
        preparation_source_fingerprint="a" * 64,
        created_at_us=NOW_US if recording_id.endswith("1" * 32) else NOW_US + 100,
        target_scope=WebTargetScope(
            base_url="http://127.0.0.1:18080",
            allowed_origins=("http://127.0.0.1:18080",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(18080,),
            allow_private_network=True,
        ),
        sessions=(
            RecordingSessionRef(
                test_identity_id="tid_0123456789abcdef0123456789abcdef",
                session_ref="session_" + "5" * 32,
                auth_method=RecordingAuthMethod.BEARER,
                bearer_ref=secret_refs[0],
                expires_at_us=NOW_US + 1_000_000,
            ),
        ),
        budget=RecordingBudget(
            max_duration_us=1_000_000,
        ),
        headless=True,
        trace_enabled=False,
    )


def captured_result(
    recording_id: str,
    *,
    project_id: str = PROJECT_ID,
    response_body: str = '{"id":"resource-42"}',
) -> RecordingRunnerResult:
    lifecycle = (
        RecordingStateEvent(
            sequence=1,
            source=RecordingState.CREATED,
            target=RecordingState.STARTING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 11,
        ),
        RecordingStateEvent(
            sequence=2,
            source=RecordingState.STARTING,
            target=RecordingState.RECORDING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 12,
        ),
        RecordingStateEvent(
            sequence=3,
            source=RecordingState.RECORDING,
            target=RecordingState.CLEANING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 13,
            reason_code="RECORDING_FINISHED",
        ),
        RecordingStateEvent(
            sequence=4,
            source=RecordingState.CLEANING,
            target=RecordingState.PROCESSING,
            operator="RECORDING_RUNNER",
            occurred_at_us=NOW_US + 14,
        ),
    )
    events = (
        RecordingEvent(
            sequence=1,
            occurred_at_us=NOW_US + 12,
            kind=RecordingEventKind.UI_SUBMIT,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            action_id="action_000001",
            element_locator="#resource-form",
        ),
        RecordingEvent(
            sequence=2,
            occurred_at_us=NOW_US + 12,
            kind=RecordingEventKind.REQUEST,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000001",
            caused_by_action_id="action_000001",
            url="http://127.0.0.1:18080/resources",
            method="POST",
            resource_type="fetch",
            body='{"name":"demo"}',
        ),
        RecordingEvent(
            sequence=3,
            occurred_at_us=NOW_US + 13,
            kind=RecordingEventKind.RESPONSE,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000001",
            url="http://127.0.0.1:18080/resources",
            status_code=201,
            headers=(
                RecordingHeader(
                    name="location",
                    value="/resources/resource-42",
                ),
            ),
            body=response_body,
        ),
        RecordingEvent(
            sequence=4,
            occurred_at_us=NOW_US + 14,
            kind=RecordingEventKind.REQUEST,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000002",
            url="http://127.0.0.1:18080/resources/resource-42",
            method="GET",
            resource_type="fetch",
        ),
        RecordingEvent(
            sequence=5,
            occurred_at_us=NOW_US + 15,
            kind=RecordingEventKind.RESPONSE,
            identity_id="tid_" + "0" * 31 + "1",
            page_id="page_000001",
            frame_id="frame_000001",
            request_id="request_000002",
            url="http://127.0.0.1:18080/resources/resource-42",
            status_code=200,
            body="{}",
        ),
    )
    return RecordingRunnerResult(
        schema_version="1",
        recording_id=recording_id,
        project_id=project_id,
        finished_at_us=NOW_US + 20,
        result_type=RecordingRunnerResultType.CAPTURED,
        recording_state=RecordingState.PROCESSING,
        cleanup_status=RecordingCleanupStatus.SUCCEEDED,
        reason_codes=("RECORDING_FINISHED",),
        state_events=lifecycle,
        events=events,
    )
