from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from jiejian.protocols.observer_v2 import (
    CausalityStatus,
    CorrelationV2,
    NormalizedStateV2,
    ObservationCompleteness,
    ObservationEnvelopeV2,
    ObservationPhase,
    ObservationProvenanceV2,
    ObservationWindowV2,
    ObserverBudgetV2,
    ObserverInvocationV2,
    ObserverOutcomeStatus,
    ObserverOutcomeV2,
    ObserverSpecV2,
    ObserverTargetV2,
    ObserverType,
    AuditLogObserverInvocationV2,
    AuditLogScanBudgetV2,
    OwnerApiLocatorV2,
    ProvenanceType,
    SqliteQueryLocatorV2,
    StructuredAuditLogLocatorV2,
    AuditLogStartCursorV2,
    AsyncTaskObserverInvocationV2,
    AzureBlobObjectLocatorV2,
    AzureQueuePeekLocatorV2,
    BlobObjectScanBudgetV2,
    build_normalized_state,
    canonical_json_bytes,
    canonical_sha256,
    evaluate_observer_outcome,
    parse_observer_json,
    QueuePeekBudgetV2,
)
from jiejian.verification.owner_api_observer import (
    OwnerApiObserverV2Adapter,
    project_owner_envelope_to_v1,
)
from jiejian.redaction import redact_known_secrets


def _complete_envelope() -> ObservationEnvelopeV2:
    state = build_normalized_state({"status_code": 200, "data": {"value": "safe"}})
    return ObservationEnvelopeV2(
        observer_id="owner_api",
        observer_type=ObserverType.OWNER_API,
        phase=ObservationPhase.AFTER,
        target_id="owner-api-state",
        window=ObservationWindowV2(phase=ObservationPhase.AFTER, started_at_us=100, finished_at_us=200, timeout_us=1000),
        correlation=CorrelationV2(case_id="case-1", resource_id="document", request_marker="case-1"),
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenanceV2(
            provenance_type=ProvenanceType.OWNER_API,
            adapter_version="owner-api-v2-compat-1",
            target_id="owner-api-state",
            source_sha256=canonical_sha256({"status_code": 200, "data": {"value": "safe"}}),
        ),
    )


def test_observer_v2_strict_round_trip_and_canonical_hash() -> None:
    envelope = _complete_envelope()
    raw = canonical_json_bytes(envelope)
    assert parse_observer_json(raw, ObservationEnvelopeV2) == envelope
    assert canonical_sha256(envelope) == hashlib.sha256(raw).hexdigest()
    assert canonical_json_bytes(envelope) == canonical_json_bytes(ObservationEnvelopeV2.model_validate_json(raw))


@pytest.mark.parametrize(
    ("schema_name", "model_type"),
    [
        ("observer-spec-v2.schema.json", ObserverSpecV2),
        ("observation-envelope-v2.schema.json", ObservationEnvelopeV2),
        ("observer-outcome-v2.schema.json", ObserverOutcomeV2),
    ("observer-invocation-v2.schema.json", ObserverInvocationV2),
        ("audit-log-observer-invocation-v2.schema.json", AuditLogObserverInvocationV2),
        ("async-task-observer-invocation-v2.schema.json", AsyncTaskObserverInvocationV2),
    ],
)
def test_checked_in_observer_schema_has_no_drift(schema_name: str, model_type: type) -> None:
    checked_in = json.loads((Path("schemas/observer") / schema_name).read_text(encoding="utf-8"))
    assert checked_in == model_type.model_json_schema()


def test_locator_types_and_secret_boundaries_are_strict() -> None:
    owner = ObserverSpecV2(
        observer_id="owner_api",
        observer_type=ObserverType.OWNER_API,
        target=ObserverTargetV2(
            target_id="owner-api-state",
            locator=OwnerApiLocatorV2(relative_path_template="/owner/resources/{resource_id}"),
            normalization_id="owner-api-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER, ObservationPhase.BEFORE),
        required=True,
        budget=ObserverBudgetV2(timeout_us=1000, max_rows=1, max_bytes=4096),
    )
    assert owner.phases == (ObservationPhase.AFTER, ObservationPhase.BEFORE)
    sqlite = ObserverSpecV2(
        observer_id="sqlite_observer",
        observer_type=ObserverType.READ_ONLY_SQLITE,
        target=ObserverTargetV2(
            target_id="sqlite-state",
            locator=SqliteQueryLocatorV2(query_template_id="resource-state", table_or_view="resource_state", database_secret_ref="env:DB_SECRET"),
            normalization_id="resource-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER,),
        required=False,
        budget=ObserverBudgetV2(timeout_us=1000, max_rows=10, max_bytes=4096),
    )
    assert sqlite.target.locator.locator_type == "READ_ONLY_SQLITE"
    with pytest.raises(ValueError):
        OwnerApiLocatorV2(relative_path_template="https://example.test/{resource_id}")
    with pytest.raises(ValueError):
        SqliteQueryLocatorV2(query_template_id="resource-state", table_or_view="resource_state", database_secret_ref="token=inline")
    with pytest.raises(ValueError):
        ObserverSpecV2(
            observer_id="owner_api",
            observer_type=ObserverType.OWNER_API,
            target=sqlite.target,
            phases=(ObservationPhase.AFTER,),
            required=True,
            budget=ObserverBudgetV2(timeout_us=1000, max_rows=1, max_bytes=4096),
        )


def _azure_queue_spec(**overrides: object) -> ObserverSpecV2:
    values: dict[str, object] = {
        "observer_id": "azure_queue",
        "observer_type": ObserverType.AZURE_QUEUE_PEEK,
        "target": ObserverTargetV2(
            target_id="queue-state",
            locator=AzureQueuePeekLocatorV2(
                service_url="https://acct.queue.core.windows.net",
                queue_name="case-queue",
                read_only_sas_ref="env:QUEUE_SAS",
                allow_loopback_http=False,
                exclusive_test_queue=True,
                allowed_fields=("resource_id", "event_id", "case_tag", "sequence"),
                peek_budget=QueuePeekBudgetV2(
                    max_messages=4,
                    max_message_bytes=512,
                    max_total_bytes=2048,
                    max_attempts=2,
                    per_request_timeout_us=1000,
                    retry_interval_us=100,
                ),
            ),
            normalization_id="queue-state",
            normalization_version="1.0",
        ),
        "phases": (ObservationPhase.EVENTUAL,),
        "required": True,
        "budget": ObserverBudgetV2(timeout_us=30_000, max_rows=4, max_bytes=2048),
    }
    values.update(overrides)
    return ObserverSpecV2(**values)


def _azure_blob_spec(**overrides: object) -> ObserverSpecV2:
    values: dict[str, object] = {
        "observer_id": "azure_blob",
        "observer_type": ObserverType.AZURE_BLOB_OBJECT,
        "target": ObserverTargetV2(
            target_id="blob-state",
            locator=AzureBlobObjectLocatorV2(
                service_url="https://acct.blob.core.windows.net",
                container_name="case-container",
                prefix_template="cases/{request_marker}/",
                read_only_sas_ref="env:BLOB_SAS",
                allow_loopback_http=False,
                exclusive_test_container=True,
                allowed_metadata_fields=("resource_id", "case_tag"),
                scan_budget=BlobObjectScanBudgetV2(
                    page_size=2,
                    max_pages=4,
                    max_objects=4,
                    max_object_bytes=512,
                    max_total_bytes=2048,
                    max_attempts=2,
                    per_request_timeout_us=1000,
                    retry_interval_us=100,
                ),
            ),
            normalization_id="blob-state",
            normalization_version="1.0",
        ),
        "phases": (ObservationPhase.BEFORE, ObservationPhase.AFTER, ObservationPhase.EVENTUAL),
        "required": True,
        "budget": ObserverBudgetV2(timeout_us=30_000, max_rows=4, max_bytes=2048),
    }
    values.update(overrides)
    return ObserverSpecV2(**values)


def test_azure_queue_and_blob_specs_are_strict_and_use_existing_invocation() -> None:
    queue = _azure_queue_spec()
    blob = _azure_blob_spec()
    assert queue.target.locator.locator_type == "AZURE_QUEUE_PEEK"
    assert blob.target.locator.locator_type == "AZURE_BLOB_OBJECT"
    queue_invocation = ObserverInvocationV2(
        spec=queue,
        correlation=CorrelationV2(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        phase=ObservationPhase.EVENTUAL,
    )
    blob_invocation = ObserverInvocationV2(
        spec=blob,
        correlation=CorrelationV2(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        phase=ObservationPhase.BEFORE,
    )
    assert queue_invocation.phase is ObservationPhase.EVENTUAL
    assert blob_invocation.phase is ObservationPhase.BEFORE


@pytest.mark.parametrize(
    "locator",
    [
        AzureQueuePeekLocatorV2(
            service_url="http://127.0.0.1:10001/devstoreaccount1",
            queue_name="case-queue",
            read_only_sas_ref="env:QUEUE_SAS",
            allow_loopback_http=True,
            exclusive_test_queue=True,
            allowed_fields=("case_tag", "event_id", "resource_id", "sequence"),
            peek_budget=QueuePeekBudgetV2(max_messages=1, max_message_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0),
        ),
        AzureBlobObjectLocatorV2(
            service_url="http://127.0.0.1:10000/devstoreaccount1",
            container_name="case-container",
            prefix_template="cases/{request_marker}/",
            read_only_sas_ref="env:BLOB_SAS",
            allow_loopback_http=True,
            exclusive_test_container=True,
            allowed_metadata_fields=("case_tag", "resource_id"),
            scan_budget=BlobObjectScanBudgetV2(page_size=1, max_pages=1, max_objects=1, max_object_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0),
        ),
    ],
)
def test_azure_loopback_fixture_is_representable(locator: object) -> None:
    assert locator.allow_loopback_http is True


@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (AzureQueuePeekLocatorV2, {"service_url": "https://example.com", "queue_name": "case-queue", "read_only_sas_ref": "env:Q", "allow_loopback_http": False, "exclusive_test_queue": True, "allowed_fields": ("case_tag", "event_id", "resource_id", "sequence"), "peek_budget": QueuePeekBudgetV2(max_messages=1, max_message_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0)}),
        (AzureBlobObjectLocatorV2, {"service_url": "https://acct.blob.core.windows.net", "container_name": "case-container", "prefix_template": "cases/{request_marker}/../", "read_only_sas_ref": "env:B", "allow_loopback_http": False, "exclusive_test_container": True, "allowed_metadata_fields": ("case_tag", "resource_id"), "scan_budget": BlobObjectScanBudgetV2(page_size=1, max_pages=1, max_objects=1, max_object_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0)}),
    ],
)
def test_azure_endpoint_namespace_and_prefix_boundaries_are_rejected(factory: type, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        factory(**kwargs)
    if factory is AzureQueuePeekLocatorV2:
        with pytest.raises(ValueError):
            factory(**{**kwargs, "service_url": "http://localhost:10001/devstoreaccount1"})
        with pytest.raises(ValueError):
            factory(**{**kwargs, "service_url": "https://acct.blob.core.windows.net"})


def test_azure_budget_phase_field_and_secret_constraints_are_rejected() -> None:
    with pytest.raises(ValueError):
        _azure_queue_spec(phases=(ObservationPhase.AFTER,))
    with pytest.raises(ValueError):
        _azure_blob_spec(phases=(ObservationPhase.INITIAL,))
    with pytest.raises(ValueError):
        _azure_queue_spec(budget=ObserverBudgetV2(timeout_us=1, max_rows=4, max_bytes=2048))
    with pytest.raises(ValueError):
        AzureQueuePeekLocatorV2(
            service_url="https://acct.queue.core.windows.net",
            queue_name="case-queue",
            read_only_sas_ref="sas-inline",
            allow_loopback_http=False,
            exclusive_test_queue=True,
            allowed_fields=("case_tag", "event_id", "resource_id", "sequence"),
            peek_budget=QueuePeekBudgetV2(max_messages=1, max_message_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0),
        )
    with pytest.raises(ValueError):
        AzureQueuePeekLocatorV2(
            service_url="https://acct.queue.core.windows.net",
            queue_name="a--queue",
            read_only_sas_ref="env:QUEUE_SAS",
            allow_loopback_http=False,
            exclusive_test_queue=True,
            allowed_fields=("case_tag", "event_id", "resource_id", "sequence"),
            peek_budget=QueuePeekBudgetV2(max_messages=1, max_message_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0),
        )


@pytest.mark.parametrize(
    ("observer_type", "provenance_type"),
    [
        (ObserverType.AZURE_QUEUE_PEEK, ProvenanceType.AZURE_QUEUE_PEEK),
        (ObserverType.AZURE_BLOB_OBJECT, ProvenanceType.AZURE_BLOB_OBJECT),
    ],
)
def test_azure_envelope_provenance_mapping_is_explicit(observer_type: ObserverType, provenance_type: ProvenanceType) -> None:
    state = build_normalized_state({"objects": []})
    target_id = "queue-state" if observer_type is ObserverType.AZURE_QUEUE_PEEK else "blob-state"
    envelope = ObservationEnvelopeV2(
        observer_id="azure_observer",
        observer_type=observer_type,
        phase=ObservationPhase.EVENTUAL,
        target_id=target_id,
        window=ObservationWindowV2(phase=ObservationPhase.EVENTUAL, started_at_us=1, finished_at_us=2, timeout_us=10),
        correlation=CorrelationV2(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenanceV2(
            provenance_type=provenance_type,
            adapter_version="azure-observer-v2",
            target_id=target_id,
            source_sha256=canonical_sha256({"objects": []}),
        ),
    )
    assert evaluate_observer_outcome(envelope, required=True).status is ObserverOutcomeStatus.AVAILABLE
    with pytest.raises(ValueError):
        ObservationProvenanceV2(
            provenance_type=provenance_type,
            adapter_version="azure-observer-v2",
            target_id=target_id,
            query_template_id="not-allowed",
            source_sha256="a" * 64,
        )


def test_legacy_63_spec_and_invocation_canonical_sentinels_remain_unchanged() -> None:
    owner = ObserverSpecV2(
        observer_id="owner_api",
        observer_type=ObserverType.OWNER_API,
        target=ObserverTargetV2(
            target_id="owner-api-state",
            locator=OwnerApiLocatorV2(relative_path_template="/owner/resources/{resource_id}"),
            normalization_id="owner-api-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER,),
        required=True,
        budget=ObserverBudgetV2(timeout_us=1_000_000, max_rows=1, max_bytes=4096),
    )
    sqlite = ObserverSpecV2(
        observer_id="sqlite_observer",
        observer_type=ObserverType.READ_ONLY_SQLITE,
        target=ObserverTargetV2(
            target_id="sqlite-state",
            locator=SqliteQueryLocatorV2(
                query_template_id="resource-state",
                table_or_view="resource_state",
                database_secret_ref="env:DB_SECRET",
            ),
            normalization_id="resource-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER,),
        required=True,
        budget=ObserverBudgetV2(timeout_us=1_000_000, max_rows=10, max_bytes=4096),
    )
    invocation = ObserverInvocationV2(
        spec=sqlite,
        correlation=CorrelationV2(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        phase=ObservationPhase.AFTER,
    )
    expected = (
        "7b22627564676574223a7b226d61785f6279746573223a343039362c226d61785f726f7773223a312c22736368656d615f76657273696f6e223a2232222c226d61785f726f7773223a312c2274696d656f75745f7573223a313030303030307d",
        "37f68b92bd53781ba778ce5c1936cc1bb69f5456217416f6fce903c9656f34ce",
    )
    assert canonical_sha256(owner) == "37f68b92bd53781ba778ce5c1936cc1bb69f5456217416f6fce903c9656f34ce"
    assert canonical_json_bytes(owner).startswith(b'{"budget"')
    assert canonical_sha256(sqlite) == "7c3b331a04439a36ec015696db9fe3f106917332a0981e8841c15b75c2ce5121"
    assert canonical_sha256(invocation) == "8a32a7cbf8dbe91cc4243719f93578b2291b3581bb41b563486a50792760fe85"
    audit = ObserverSpecV2(
        observer_id="audit_observer",
        observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
        target=ObserverTargetV2(
            target_id="audit-window",
            locator=StructuredAuditLogLocatorV2(
                authorized_root_ref="env:AUDIT_ROOT",
                relative_file_pattern="audit.jsonl",
                allowed_fields=("resource_id", "event_id", "case_tag", "task_id", "event_type", "sequence"),
                scan_budget=AuditLogScanBudgetV2(max_files=4, max_lines=100, max_line_bytes=4096),
            ),
            normalization_id="audit-window",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER, ObservationPhase.EVENTUAL),
        required=True,
        budget=ObserverBudgetV2(timeout_us=1000, max_rows=20, max_bytes=4096),
    )
    assert audit.target.locator.allowed_fields == ("case_tag", "event_id", "event_type", "resource_id", "sequence", "task_id")
    invocation = AuditLogObserverInvocationV2(
        spec=audit,
        correlation=CorrelationV2(case_id="case-1", resource_id="resource", request_marker="case-1"),
        phase=ObservationPhase.EVENTUAL,
        start_cursors=(AuditLogStartCursorV2(file_name="audit.1.jsonl", offset=0),),
    )
    assert invocation.start_cursors[0].file_name == "audit.1.jsonl"
    with pytest.raises(ValueError, match="require AuditLogObserverInvocationV2"):
        ObserverInvocationV2(
            spec=audit,
            correlation=invocation.correlation,
            phase=ObservationPhase.EVENTUAL,
        )
    with pytest.raises(ValueError):
        AuditLogObserverInvocationV2(
            spec=audit,
            correlation=invocation.correlation,
            phase=ObservationPhase.AFTER,
            start_cursors=(AuditLogStartCursorV2(file_name="other.jsonl", offset=0),),
        )


def test_observation_completeness_matrix_and_outcome_never_decides_verdict() -> None:
    complete = _complete_envelope()
    assert evaluate_observer_outcome(complete, required=True).status is ObserverOutcomeStatus.AVAILABLE
    missing = complete.model_copy(update={"completeness": ObservationCompleteness.MISSING, "state": None, "provenance": None, "reason_codes": ("OWNER_API_UNAVAILABLE",)})
    assert evaluate_observer_outcome(missing, required=True).status is ObserverOutcomeStatus.INCONCLUSIVE
    assert evaluate_observer_outcome(missing, required=False).status is ObserverOutcomeStatus.AVAILABLE
    assert evaluate_observer_outcome(complete, required=True, adapter_error=True).status is ObserverOutcomeStatus.EXECUTION_ERROR
    with pytest.raises(ValueError):
        ObservationEnvelopeV2(**complete.model_dump(mode="python", exclude={"completeness", "reason_codes"}), completeness=ObservationCompleteness.MISSING, reason_codes=())
    partial = complete.model_copy(update={"completeness": ObservationCompleteness.PARTIAL, "reason_codes": ("PARTIAL_STATE",)})
    assert partial.state is not None
    with pytest.raises(ValueError):
        invalid_provenance = complete.model_dump(mode="python")
        invalid_provenance["provenance"] = complete.provenance.model_copy(update={"target_id": "other-target"})
        ObservationEnvelopeV2(**invalid_provenance)
    audit_state = build_normalized_state({"records": [{"event_id": "event-1"}]})
    audit = ObservationEnvelopeV2(
        observer_id="audit_observer",
        observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
        phase=ObservationPhase.EVENTUAL,
        target_id="audit-window",
        window=ObservationWindowV2(phase=ObservationPhase.EVENTUAL, started_at_us=100, finished_at_us=200, timeout_us=1000),
        correlation=CorrelationV2(case_id="case-1", resource_id="document", request_marker="case-1"),
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=audit_state,
        provenance=ObservationProvenanceV2(
            provenance_type=ProvenanceType.AUDIT_LOG_WINDOW,
            adapter_version="audit-log-observer-1",
            target_id="audit-window",
            source_sha256=canonical_sha256([{"event_id": "event-1"}]),
        ),
    )
    assert evaluate_observer_outcome(audit, required=True).status is ObserverOutcomeStatus.AVAILABLE
    with pytest.raises(ValueError):
        ObservationEnvelopeV2(**(audit.model_dump(mode="python") | {"provenance": audit.provenance.model_copy(update={"provenance_type": ProvenanceType.SQLITE_QUERY, "query_template_id": "resource-state"})}))


def test_observer_json_rejects_duplicate_bom_nonfinite_and_known_secret() -> None:
    raw = b'{"schema_version":"2","schema_version":"2"}'
    with pytest.raises(ValueError):
        parse_observer_json(raw, ObserverBudgetV2)
    with pytest.raises(ValueError):
        parse_observer_json(b'{"schema_version":"2","event_id":"a","event_id":"b"}', StructuredAuditLogLocatorV2)
    with pytest.raises(ValueError):
        parse_observer_json(b"\xef\xbb\xbf{}", ObserverBudgetV2)
    with pytest.raises(ValueError):
        parse_observer_json(b'{"timeout_us":NaN,"max_rows":1,"max_bytes":10}', ObserverBudgetV2)
    with pytest.raises(ValueError):
        build_normalized_state({"echo": "token-secret"}, known_secrets=("token-secret",))
    with pytest.raises(ValueError):
        build_normalized_state({"token-secret": "safe"}, known_secrets=("token-secret",))
    with pytest.raises(ValueError):
        parse_observer_json(
            b'{"schema_version":"2","canonical_data":{"token-secret":"safe"},"canonical_sha256":"' + canonical_sha256({"token-secret": "safe"}).encode() + b'","byte_count":23}',
            NormalizedStateV2,
            known_secrets=("token-secret",),
        )
    state = build_normalized_state({"b": 2, "a": 1})
    assert state.canonical_data == {"a": 1, "b": 2}


def test_owner_api_adapter_projects_complete_envelope_to_identical_v1_observation() -> None:
    class Response:
        status_code = 200
        data = {"value": "new"}

    class Executor:
        def request(self, *args, **kwargs):
            assert args[:2] == ("GET", "/owner/resources/document")
            assert kwargs["bearer_token"] == "owner-token"
            return Response()

    ticks = iter((100, 200))
    adapter = OwnerApiObserverV2Adapter.for_path(
        "/owner/resources/{resource_id}", timeout_us=1000, max_bytes=4096, utc_now_us=lambda: next(ticks)
    )
    envelope = adapter.observe(
        Executor(), resource_id="document", owner_token="owner-token", case_id="case-1", phase=ObservationPhase.AFTER
    )
    projected = project_owner_envelope_to_v1(envelope)
    assert projected.model_dump(mode="python") == {"schema_version": "1", "observer": "owner_api", "phase": "after", "status_code": 200, "data": {"value": "new"}}
    assert "owner-token" not in canonical_json_bytes(envelope).decode("utf-8")


def test_owner_api_adapter_preserves_v1_redaction_for_sensitive_payloads() -> None:
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

    adapter = OwnerApiObserverV2Adapter.for_path(
        "/owner/resources/{resource_id}", timeout_us=1000, max_bytes=4096, utc_now_us=lambda: 100
    )
    envelope = adapter.observe(
        Executor(), resource_id="document", owner_token="owner-token", case_id="case-1", phase=ObservationPhase.AFTER, known_secrets=("owner-token",)
    )
    projected = project_owner_envelope_to_v1(envelope)
    expected = redact_known_secrets(Response.data, ("owner-token",))
    assert envelope.state is not None
    assert envelope.state.canonical_data["data"] == expected
    assert projected.data == expected
    serialized = canonical_json_bytes(envelope).decode("utf-8")
    for secret in ("password-value", "response-token", "nested-token", "owner-token"):
        assert secret not in serialized
    assert serialized.count("[REDACTED]") >= 4


def test_owner_api_adapter_non_2xx_is_unavailable_and_cannot_project_to_v1() -> None:
    class Response:
        status_code = 503
        data = {"error": "unavailable"}

    class Executor:
        def request(self, *args, **kwargs):
            return Response()

    adapter = OwnerApiObserverV2Adapter.for_path(
        "/owner/resources/{resource_id}", timeout_us=1000, max_bytes=4096, utc_now_us=lambda: 100
    )
    envelope = adapter.observe(
        Executor(), resource_id="document", owner_token="owner-token", case_id="case-1", phase=ObservationPhase.AFTER
    )
    assert envelope.completeness is ObservationCompleteness.MISSING
    with pytest.raises(ValueError):
        project_owner_envelope_to_v1(envelope)
