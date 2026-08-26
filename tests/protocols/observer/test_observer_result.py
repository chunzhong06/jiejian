# 验证 Observer 结果、完整性、归一状态与 canonical/hash 边界。

from __future__ import annotations
import hashlib
import json
from pathlib import Path
import pytest
from product.protocols.observer import (
    CausalityStatus,
    Correlation,
    NormalizedState,
    ObservationCompleteness,
    ObservationEnvelope,
    ObservationPhase,
    ObservationProvenance,
    ObservationWindow,
    ObserverBudget,
    ObserverInvocation,
    ObserverOutcomeStatus,
    ObserverOutcome,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    AuditLogObserverInvocation,
    AuditLogScanBudget,
    OwnerApiLocator,
    ProvenanceType,
    SqliteQueryLocator,
    StructuredAuditLogLocator,
    AuditLogStartCursor,
    AsyncTaskObserverInvocation,
    AzureBlobObjectLocator,
    AzureQueuePeekLocator,
    BlobObjectScanBudget,
    build_normalized_state,
    canonical_json_bytes,
    observer_canonical_sha256,
    evaluate_observer_outcome,
    parse_observer_json,
    QueuePeekBudget,
)
from product.backend.infra.observers.owner_api import (
    OwnerApiObserverAdapter,
)
from product.backend.core.redaction import redact_known_secrets
pytestmark = pytest.mark.essential

def _complete_envelope() -> ObservationEnvelope:
    state = build_normalized_state({"status_code": 200, "data": {"value": "safe"}})
    return ObservationEnvelope(
        observer_id="owner_api",
        observer_type=ObserverType.OWNER_API,
        phase=ObservationPhase.AFTER,
        target_id="owner-api-state",
        window=ObservationWindow(phase=ObservationPhase.AFTER, started_at_us=100, finished_at_us=200, timeout_us=1000),
        correlation=Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenance(
            provenance_type=ProvenanceType.OWNER_API,
            adapter_version="owner-api-1",
            target_id="owner-api-state",
            source_sha256=observer_canonical_sha256({"status_code": 200, "data": {"value": "safe"}}),
        ),
    )

def test_observer_strict_round_trip_and_canonical_hash() -> None:
    envelope = _complete_envelope()
    raw = canonical_json_bytes(envelope)
    assert parse_observer_json(raw, ObservationEnvelope) == envelope
    assert observer_canonical_sha256(envelope) == hashlib.sha256(raw).hexdigest()
    assert canonical_json_bytes(envelope) == canonical_json_bytes(ObservationEnvelope.model_validate_json(raw))

@pytest.mark.parametrize("schema_name, model_type", [("observer-spec.schema.json", ObserverSpec), ("observation-envelope.schema.json", ObservationEnvelope), ("observer-outcome.schema.json", ObserverOutcome), ("observer-invocation.schema.json", ObserverInvocation), ("audit-log-observer-invocation.schema.json", AuditLogObserverInvocation), ("async-task-observer-invocation.schema.json", AsyncTaskObserverInvocation)])
def test_checked_in_observer_schema_has_no_drift(schema_name: str, model_type: type) -> None:
    checked_in = json.loads((Path("product/protocols/schemas/observer") / schema_name).read_text(encoding="utf-8"))
    assert checked_in == model_type.model_json_schema()

@pytest.mark.parametrize(("observer_type", "provenance_type"), [(ObserverType.AZURE_QUEUE_PEEK, ProvenanceType.AZURE_QUEUE_PEEK), (ObserverType.AZURE_BLOB_OBJECT, ProvenanceType.AZURE_BLOB_OBJECT)])
def test_azure_envelope_provenance_mapping_is_explicit(observer_type: ObserverType, provenance_type: ProvenanceType) -> None:
    state = build_normalized_state({"objects": []})
    target_id = "queue-state" if observer_type is ObserverType.AZURE_QUEUE_PEEK else "blob-state"
    envelope = ObservationEnvelope(
        observer_id="azure_observer",
        observer_type=observer_type,
        phase=ObservationPhase.EVENTUAL,
        target_id=target_id,
        window=ObservationWindow(phase=ObservationPhase.EVENTUAL, started_at_us=1, finished_at_us=2, timeout_us=10),
        correlation=Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenance(
            provenance_type=provenance_type,
            adapter_version="azure-observer-v2",
            target_id=target_id,
            source_sha256=observer_canonical_sha256({"objects": []}),
        ),
    )
    assert evaluate_observer_outcome(envelope, required=True).status is ObserverOutcomeStatus.AVAILABLE
    with pytest.raises(ValueError):
        ObservationProvenance(
            provenance_type=provenance_type,
            adapter_version="azure-observer-v2",
            target_id=target_id,
            query_template_id="not-allowed",
            source_sha256="a" * 64,
        )

def test_observation_completeness_matrix_and_outcome_never_decides_verdict() -> None:
    complete = _complete_envelope()
    assert evaluate_observer_outcome(complete, required=True).status is ObserverOutcomeStatus.AVAILABLE
    missing = complete.model_copy(update={"completeness": ObservationCompleteness.MISSING, "state": None, "provenance": None, "reason_codes": ("OWNER_API_UNAVAILABLE",)})
    assert evaluate_observer_outcome(missing, required=True).status is ObserverOutcomeStatus.INCONCLUSIVE
    assert evaluate_observer_outcome(missing, required=False).status is ObserverOutcomeStatus.AVAILABLE
    assert evaluate_observer_outcome(complete, required=True, adapter_error=True).status is ObserverOutcomeStatus.EXECUTION_ERROR
    with pytest.raises(ValueError):
        ObservationEnvelope(**complete.model_dump(mode="python", exclude={"completeness", "reason_codes"}), completeness=ObservationCompleteness.MISSING, reason_codes=())
    partial = complete.model_copy(update={"completeness": ObservationCompleteness.PARTIAL, "reason_codes": ("PARTIAL_STATE",)})
    assert partial.state is not None
    with pytest.raises(ValueError):
        invalid_provenance = complete.model_dump(mode="python")
        invalid_provenance["provenance"] = complete.provenance.model_copy(update={"target_id": "other-target"})
        ObservationEnvelope(**invalid_provenance)
    audit_state = build_normalized_state({"records": [{"event_id": "event-1"}]})
    audit = ObservationEnvelope(
        observer_id="audit_observer",
        observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
        phase=ObservationPhase.EVENTUAL,
        target_id="audit-window",
        window=ObservationWindow(phase=ObservationPhase.EVENTUAL, started_at_us=100, finished_at_us=200, timeout_us=1000),
        correlation=Correlation(case_id="case-1", resource_id="document", request_marker="case-1"),
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=audit_state,
        provenance=ObservationProvenance(
            provenance_type=ProvenanceType.AUDIT_LOG_WINDOW,
            adapter_version="audit-log-observer-1",
            target_id="audit-window",
            source_sha256=observer_canonical_sha256([{"event_id": "event-1"}]),
        ),
    )
    assert evaluate_observer_outcome(audit, required=True).status is ObserverOutcomeStatus.AVAILABLE
    with pytest.raises(ValueError):
        ObservationEnvelope(**(audit.model_dump(mode="python") | {"provenance": audit.provenance.model_copy(update={"provenance_type": ProvenanceType.SQLITE_QUERY, "query_template_id": "resource-state"})}))

def test_owner_api_adapter_emits_current_complete_envelope() -> None:
    class Response:
        status_code = 200
        data = {"value": "new"}

    class Executor:
        def request(self, *args, **kwargs):
            assert args[:2] == ("GET", "/owner/resources/document")
            assert kwargs["redaction_values"] == ("owner-token",)
            return Response()

    ticks = iter((100, 200))
    adapter = OwnerApiObserverAdapter.for_path(
        "/owner/resources/{resource_id}", timeout_us=1000, max_bytes=4096, utc_now_us=lambda: next(ticks)
    )
    envelope = adapter.observe(
        Executor(), resource_id="document", owner_token="owner-token", case_id="case-1", phase=ObservationPhase.AFTER
    )
    assert envelope.observer_id == "owner_api"
    assert envelope.state is not None
    assert envelope.state.canonical_data == {"data": {"value": "new"}, "status_code": 200}
    assert "owner-token" not in canonical_json_bytes(envelope).decode("utf-8")

def test_owner_api_adapter_preserves_redaction_for_sensitive_payloads() -> None:
    class Response:
        status_code = 200
        data = {
            "password": "password-value",
            "Authorization": "Bearer response-token",
            "nested": {"token": "nested-token", "note": "owner-token"},
            "safe": "value",
        }

    class Executor:
        def request(self, *args, **kwargs):
            return Response()

    adapter = OwnerApiObserverAdapter.for_path(
        "/owner/resources/{resource_id}", timeout_us=1000, max_bytes=4096, utc_now_us=lambda: 100
    )
    envelope = adapter.observe(
        Executor(), resource_id="document", owner_token="owner-token", case_id="case-1", phase=ObservationPhase.AFTER, known_secrets=("owner-token",)
    )
    expected = redact_known_secrets(Response.data, ("owner-token",))
    assert envelope.state is not None
    assert envelope.state.canonical_data["data"] == expected
    serialized = canonical_json_bytes(envelope).decode("utf-8")
    for secret in ("password-value", "response-token", "nested-token", "owner-token"):
        assert secret not in serialized
    assert serialized.count("[REDACTED]") >= 4

def test_owner_api_adapter_non_2xx_is_unavailable() -> None:
    class Response:
        status_code = 503
        data = {"error": "unavailable"}

    class Executor:
        def request(self, *args, **kwargs):
            return Response()

    adapter = OwnerApiObserverAdapter.for_path(
        "/owner/resources/{resource_id}", timeout_us=1000, max_bytes=4096, utc_now_us=lambda: 100
    )
    envelope = adapter.observe(
        Executor(), resource_id="document", owner_token="owner-token", case_id="case-1", phase=ObservationPhase.AFTER
    )
    assert envelope.completeness is ObservationCompleteness.MISSING
