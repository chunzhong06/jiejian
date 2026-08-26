# 验证 Observer invocation 的关联、游标与窗口 canonical 边界。

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

def test_observer_spec_and_invocation_canonical_sentinels_remain_unchanged() -> None:
    owner = ObserverSpec(
        observer_id="owner_api",
        observer_type=ObserverType.OWNER_API,
        target=ObserverTarget(
            target_id="owner-api-state",
            locator=OwnerApiLocator(relative_path_template="/owner/resources/{resource_id}"),
            normalization_id="owner-api-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER,),
        required=True,
        budget=ObserverBudget(timeout_us=1_000_000, max_rows=1, max_bytes=4096),
    )
    sqlite = ObserverSpec(
        observer_id="sqlite_observer",
        observer_type=ObserverType.READ_ONLY_SQLITE,
        target=ObserverTarget(
            target_id="sqlite-state",
            locator=SqliteQueryLocator(
                query_template_id="resource-state",
                table_or_view="resource_state",
                database_secret_ref="env:DB_SECRET",
            ),
            normalization_id="resource-state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER,),
        required=True,
        budget=ObserverBudget(timeout_us=1_000_000, max_rows=10, max_bytes=4096),
    )
    invocation = ObserverInvocation(
        spec=sqlite,
        correlation=Correlation(case_id="case-1", resource_id="resource-a", request_marker="case-1"),
        phase=ObservationPhase.AFTER,
    )
    expected = (
        "7b22627564676574223a7b226d61785f6279746573223a343039362c226d61785f726f7773223a312c22736368656d615f76657273696f6e223a2232222c226d61785f726f7773223a312c2274696d656f75745f7573223a313030303030307d",
        "37f68b92bd53781ba778ce5c1936cc1bb69f5456217416f6fce903c9656f34ce",
    )
    assert observer_canonical_sha256(owner) == "36ebc6162c6d9c7a408314a3066b375a81a7e76e47c3d22a3f224a96da291a24"
    assert canonical_json_bytes(owner).startswith(b'{"budget"')
    assert observer_canonical_sha256(sqlite) == "930d91d1ca3c6104e782334ca4276098a2540f48fd0de6a6808e0273b2d4ed4a"
    assert observer_canonical_sha256(invocation) == "5cd506a665260ea05bda3c122a4f3d2ba7e2d841e9303a79cf98653e4a1a41bd"
    audit = ObserverSpec(
        observer_id="audit_observer",
        observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
        target=ObserverTarget(
            target_id="audit-window",
            locator=StructuredAuditLogLocator(
                authorized_root_ref="env:AUDIT_ROOT",
                relative_file_pattern="audit.jsonl",
                allowed_fields=("resource_id", "event_id", "case_tag", "task_id", "event_type", "sequence"),
                scan_budget=AuditLogScanBudget(max_files=4, max_lines=100, max_line_bytes=4096),
            ),
            normalization_id="audit-window",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER, ObservationPhase.EVENTUAL),
        required=True,
        budget=ObserverBudget(timeout_us=1000, max_rows=20, max_bytes=4096),
    )
    assert audit.target.locator.allowed_fields == ("case_tag", "event_id", "event_type", "resource_id", "sequence", "task_id")
    invocation = AuditLogObserverInvocation(
        spec=audit,
        correlation=Correlation(case_id="case-1", resource_id="resource", request_marker="case-1"),
        phase=ObservationPhase.EVENTUAL,
        start_cursors=(AuditLogStartCursor(file_name="audit.1.jsonl", offset=0),),
    )
    assert invocation.start_cursors[0].file_name == "audit.1.jsonl"
    with pytest.raises(ValueError, match="require AuditLogObserverInvocation"):
        ObserverInvocation(
            spec=audit,
            correlation=invocation.correlation,
            phase=ObservationPhase.EVENTUAL,
        )
    with pytest.raises(ValueError):
        AuditLogObserverInvocation(
            spec=audit,
            correlation=invocation.correlation,
            phase=ObservationPhase.AFTER,
            start_cursors=(AuditLogStartCursor(file_name="other.jsonl", offset=0),),
        )
