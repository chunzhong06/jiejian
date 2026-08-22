from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from product.backend.core.recording import RecordingState
from product.protocols.runner import WebTargetScope
from product.backend.core.errors import JiejianError
from product.protocols import (
    RecordingBudget,
    RecordingCleanupStatus,
    RecordingEventKind,
    RecordingEvent,
    RecordingHeader,
    RecordingRunnerError,
    RecordingRunnerRequest,
    RecordingRunnerResultType,
    RecordingRunnerResult,
    RecordingSessionRef,
    canonical_recording_json_bytes,
    parse_recording_event,
    parse_recording_request,
    parse_recording_result,
)

pytestmark = pytest.mark.essential

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def recording_request() -> RecordingRunnerRequest:
    return RecordingRunnerRequest(
        schema_version="1",
        recording_id="rec_0123456789abcdef0123456789abcdef",
        project_id="ownership-recording",
        created_at_us=1_000_000,
        target_scope=WebTargetScope(
            schema_version="2",
            base_url="http://127.0.0.1:8765",
            allowed_origins=("http://127.0.0.1:8765",),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(8765,),
            allow_private_network=True,
        ),
        sessions=(
            RecordingSessionRef(
                schema_version="1",
                identity_id="owner",
                session_ref="session_0123456789abcdef0123456789abcdef",
                secret_refs=(),
                expires_at_us=2_000_000,
            ),
            RecordingSessionRef(
                schema_version="1",
                identity_id="attacker",
                session_ref="session_fedcba9876543210fedcba9876543210",
                secret_refs=(),
                expires_at_us=2_000_000,
            ),
        ),
        budget=RecordingBudget(
            schema_version="1",
            max_duration_us=10_000_000,
            max_events=128,
            max_pages=4,
            max_contexts=2,
            max_field_chars=512,
            max_body_bytes=4_096,
            max_total_payload_bytes=65_536,
        ),
    )


def recording_event() -> RecordingEvent:
    return RecordingEvent(
        schema_version="1",
        sequence=1,
        occurred_at_us=1_000_001,
        kind=RecordingEventKind.REQUEST,
        identity_id="owner",
        page_id="page_000001",
        frame_id="frame_000001",
        request_id="request_000001",
        url="http://127.0.0.1:8765/resource",
        method="GET",
        headers=(
            RecordingHeader(
                schema_version="1",
                name="authorization",
                value="[REDACTED]",
            ),
        ),
    )


def recording_result() -> RecordingRunnerResult:
    return RecordingRunnerResult(
        schema_version="1",
        recording_id="rec_0123456789abcdef0123456789abcdef",
        project_id="ownership-recording",
        finished_at_us=1_000_002,
        result_type=RecordingRunnerResultType.CAPTURED,
        recording_state=RecordingState.PROCESSING,
        cleanup_status=RecordingCleanupStatus.SUCCEEDED,
        reason_codes=("RECORDING_FINISHED",),
        events=(recording_event(),),
    )


def test_recording_protocols_are_strict_frozen_and_round_trip() -> None:
    request = recording_request()
    result = recording_result()
    event = recording_event()

    assert parse_recording_request(canonical_recording_json_bytes(request)) == request
    assert parse_recording_result(canonical_recording_json_bytes(result)) == result
    assert parse_recording_event(canonical_recording_json_bytes(event)) == event
    assert RecordingRunnerRequest.model_config["extra"] == "forbid"
    assert RecordingRunnerResult.model_config["frozen"] is True
    with pytest.raises(ValidationError):
        request.project_id = "changed"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema_version":"1","schema_version":"1"}',
        b'{"schema_version":"1","value":NaN}',
        b'\xef\xbb\xbf{"schema_version":"1"}',
        b'{"schema_version":"2"}',
        b'{"schema_version":"1","unknown":true}',
    ],
)
def test_recording_parser_rejects_non_strict_json_and_unknown_contract(raw: bytes) -> None:
    with pytest.raises(JiejianError) as captured:
        parse_recording_request(raw)
    assert captured.value.code == "RECORD_PROTOCOL_INVALID"


def test_recording_protocol_rejects_secret_material_without_echoing_it() -> None:
    sentinel = "recording-real-secret-sentinel"
    request = recording_request().model_copy(update={"project_id": sentinel})
    with pytest.raises(JiejianError) as serialized:
        canonical_recording_json_bytes(request, known_secrets=(sentinel,))
    assert serialized.value.code == "RECORD_SECRET_EXPOSED"
    assert sentinel not in str(serialized.value)
    assert sentinel not in json.dumps(serialized.value.to_dict())

    document = json.loads(canonical_recording_json_bytes(recording_request()))
    document[f"unknown-{sentinel}"] = True
    with pytest.raises(JiejianError) as parsed:
        parse_recording_request(
            json.dumps(document, separators=(",", ":")).encode(),
            known_secrets=(sentinel,),
        )
    assert parsed.value.code == "RECORD_SECRET_EXPOSED"
    assert sentinel not in str(parsed.value)
    for model in (
        RecordingRunnerRequest,
        RecordingRunnerResult,
        RecordingEvent,
    ):
        assert sentinel not in json.dumps(model.model_json_schema())


def test_recording_result_matrix_and_sensitive_headers_are_enforced() -> None:
    data = recording_result().model_dump(mode="python")
    data["recording_state"] = RecordingState.FAILED
    with pytest.raises(ValidationError):
        RecordingRunnerResult.model_validate(data)

    failed = RecordingRunnerResult(
        schema_version="1",
        recording_id="rec_0123456789abcdef0123456789abcdef",
        project_id="ownership-recording",
        finished_at_us=1_000_002,
        result_type=RecordingRunnerResultType.FAILED,
        recording_state=RecordingState.FAILED,
        cleanup_status=RecordingCleanupStatus.FAILED,
        error=RecordingRunnerError(
            schema_version="1",
            code="RECORD_CLEANUP_FAILED",
            retryable=False,
        ),
    )
    assert failed.error is not None
    with pytest.raises(ValidationError):
        RecordingHeader(
            schema_version="1",
            name="cookie",
            value="raw-cookie",
        )


@pytest.mark.parametrize(
    ("model", "schema_path"),
    [
        (
            RecordingRunnerRequest,
            PROJECT_ROOT
            / "product"
            / "protocols"
            / "schemas"
            / "recording"
            / "recording-runner-request.schema.json",
        ),
        (
            RecordingRunnerResult,
            PROJECT_ROOT
            / "product"
            / "protocols"
            / "schemas"
            / "recording"
            / "recording-runner-result.schema.json",
        ),
        (
            RecordingEvent,
            PROJECT_ROOT / "product" / "protocols" / "schemas" / "recording" / "recording-event.schema.json",
        ),
    ],
)
def test_recording_json_schema_has_no_drift(model, schema_path: Path) -> None:
    checked_in = json.loads(schema_path.read_text(encoding="utf-8"))
    assert checked_in == model.model_json_schema()
