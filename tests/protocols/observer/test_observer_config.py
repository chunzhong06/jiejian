# 验证 Observer 配置、locator、预算与秘密边界。

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

def test_locator_types_and_secret_boundaries_are_strict() -> None:
    owner = ObserverSpec(
        observer_id="owner_api",
        observer_type=ObserverType.OWNER_API,
        target=ObserverTarget(
            target_id="owner-api-state",
            locator=OwnerApiLocator(relative_path_template="/owner/resources/{resource_id}"),
            normalization_id="owner-api-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER, ObservationPhase.BEFORE),
        required=True,
        budget=ObserverBudget(timeout_us=1000, max_rows=1, max_bytes=4096),
    )
    assert owner.phases == (ObservationPhase.AFTER, ObservationPhase.BEFORE)
    sqlite = ObserverSpec(
        observer_id="sqlite_observer",
        observer_type=ObserverType.READ_ONLY_SQLITE,
        target=ObserverTarget(
            target_id="sqlite-state",
            locator=SqliteQueryLocator(query_template_id="resource-state", table_or_view="resource_state", database_secret_ref="env:DB_SECRET"),
            normalization_id="resource-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER,),
        required=False,
        budget=ObserverBudget(timeout_us=1000, max_rows=10, max_bytes=4096),
    )
    assert sqlite.target.locator.locator_type == "READ_ONLY_SQLITE"
    with pytest.raises(ValueError):
        OwnerApiLocator(relative_path_template="https://example.test/{resource_id}")
    with pytest.raises(ValueError):
        SqliteQueryLocator(query_template_id="resource-state", table_or_view="resource_state", database_secret_ref="token=inline")
    with pytest.raises(ValueError):
        ObserverSpec(
            observer_id="owner_api",
            observer_type=ObserverType.OWNER_API,
            target=sqlite.target,
            phases=(ObservationPhase.AFTER,),
            required=True,
            budget=ObserverBudget(timeout_us=1000, max_rows=1, max_bytes=4096),
        )

def _azure_queue_spec(**overrides: object) -> ObserverSpec:
    values: dict[str, object] = {
        "observer_id": "azure_queue",
        "observer_type": ObserverType.AZURE_QUEUE_PEEK,
        "target": ObserverTarget(
            target_id="queue-state",
            locator=AzureQueuePeekLocator(
                service_url="https://acct.queue.core.windows.net",
                queue_name="case-queue",
                read_only_sas_ref="env:QUEUE_SAS",
                allow_loopback_http=False,
                exclusive_test_queue=True,
                allowed_fields=("resource_id", "event_id", "case_tag", "sequence"),
                peek_budget=QueuePeekBudget(
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
        "budget": ObserverBudget(timeout_us=30_000, max_rows=4, max_bytes=2048),
    }
    values.update(overrides)
    return ObserverSpec(**values)

def _azure_blob_spec(**overrides: object) -> ObserverSpec:
    values: dict[str, object] = {
        "observer_id": "azure_blob",
        "observer_type": ObserverType.AZURE_BLOB_OBJECT,
        "target": ObserverTarget(
            target_id="blob-state",
            locator=AzureBlobObjectLocator(
                service_url="https://acct.blob.core.windows.net",
                container_name="case-container",
                prefix_template="cases/{request_marker}/",
                read_only_sas_ref="env:BLOB_SAS",
                allow_loopback_http=False,
                exclusive_test_container=True,
                allowed_metadata_fields=("resource_id", "case_tag"),
                scan_budget=BlobObjectScanBudget(
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
        "budget": ObserverBudget(timeout_us=30_000, max_rows=4, max_bytes=2048),
    }
    values.update(overrides)
    return ObserverSpec(**values)

def test_azure_queue_and_blob_specs_are_strict_and_use_existing_invocation() -> None:
    queue = _azure_queue_spec()
    blob = _azure_blob_spec()
    assert queue.target.locator.locator_type == "AZURE_QUEUE_PEEK"
    assert blob.target.locator.locator_type == "AZURE_BLOB_OBJECT"
    queue_invocation = ObserverInvocation(
        spec=queue,
        correlation=Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        phase=ObservationPhase.EVENTUAL,
    )
    blob_invocation = ObserverInvocation(
        spec=blob,
        correlation=Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        phase=ObservationPhase.BEFORE,
    )
    assert queue_invocation.phase is ObservationPhase.EVENTUAL
    assert blob_invocation.phase is ObservationPhase.BEFORE

@pytest.mark.parametrize(
    "locator",
    [
        AzureQueuePeekLocator(service_url="http://127.0.0.1:10001/devstoreaccount1", queue_name="case-queue", read_only_sas_ref="env:QUEUE_SAS", allow_loopback_http=True, exclusive_test_queue=True, allowed_fields=("case_tag", "event_id", "resource_id", "sequence"), peek_budget=QueuePeekBudget(max_messages=1, max_message_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0)),
        AzureBlobObjectLocator(service_url="http://127.0.0.1:10000/devstoreaccount1", container_name="case-container", prefix_template="cases/{request_marker}/", read_only_sas_ref="env:BLOB_SAS", allow_loopback_http=True, exclusive_test_container=True, allowed_metadata_fields=("case_tag", "resource_id"), scan_budget=BlobObjectScanBudget(page_size=1, max_pages=1, max_objects=1, max_object_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0)),
    ],
)
def test_azure_loopback_fixture_is_representable(locator: object) -> None:
    assert locator.allow_loopback_http is True

@pytest.mark.parametrize(
    ("factory", "kwargs"),
    [
        (AzureQueuePeekLocator, {"service_url": "https://example.com", "queue_name": "case-queue", "read_only_sas_ref": "env:Q", "allow_loopback_http": False, "exclusive_test_queue": True, "allowed_fields": ("case_tag", "event_id", "resource_id", "sequence"), "peek_budget": QueuePeekBudget(max_messages=1, max_message_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0)}),
        (AzureBlobObjectLocator, {"service_url": "https://acct.blob.core.windows.net", "container_name": "case-container", "prefix_template": "cases/{request_marker}/../", "read_only_sas_ref": "env:B", "allow_loopback_http": False, "exclusive_test_container": True, "allowed_metadata_fields": ("case_tag", "resource_id"), "scan_budget": BlobObjectScanBudget(page_size=1, max_pages=1, max_objects=1, max_object_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0)}),
    ],
)
def test_azure_endpoint_namespace_and_prefix_boundaries_are_rejected(factory: type, kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        factory(**kwargs)
    if factory is AzureQueuePeekLocator:
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
        _azure_queue_spec(budget=ObserverBudget(timeout_us=1, max_rows=4, max_bytes=2048))
    with pytest.raises(ValueError):
        AzureQueuePeekLocator(
            service_url="https://acct.queue.core.windows.net",
            queue_name="case-queue",
            read_only_sas_ref="sas-inline",
            allow_loopback_http=False,
            exclusive_test_queue=True,
            allowed_fields=("case_tag", "event_id", "resource_id", "sequence"),
            peek_budget=QueuePeekBudget(max_messages=1, max_message_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0),
        )
    with pytest.raises(ValueError):
        AzureQueuePeekLocator(
            service_url="https://acct.queue.core.windows.net",
            queue_name="a--queue",
            read_only_sas_ref="env:QUEUE_SAS",
            allow_loopback_http=False,
            exclusive_test_queue=True,
            allowed_fields=("case_tag", "event_id", "resource_id", "sequence"),
            peek_budget=QueuePeekBudget(max_messages=1, max_message_bytes=1, max_total_bytes=1, max_attempts=1, per_request_timeout_us=1, retry_interval_us=0),
        )
