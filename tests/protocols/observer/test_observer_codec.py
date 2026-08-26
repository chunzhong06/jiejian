# 验证 Observer 严格 JSON codec、canonical 与秘密拒绝边界。

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

def test_observer_json_rejects_duplicate_bom_nonfinite_and_known_secret() -> None:
    raw = b'{"schema_version":"2","schema_version":"2"}'
    with pytest.raises(ValueError):
        parse_observer_json(raw, ObserverBudget)
    with pytest.raises(ValueError):
        parse_observer_json(b'{"schema_version":"2","event_id":"a","event_id":"b"}', StructuredAuditLogLocator)
    with pytest.raises(ValueError):
        parse_observer_json(b"\xef\xbb\xbf{}", ObserverBudget)
    with pytest.raises(ValueError):
        parse_observer_json(b'{"timeout_us":NaN,"max_rows":1,"max_bytes":10}', ObserverBudget)
    with pytest.raises(ValueError):
        build_normalized_state({"echo": "token-secret"}, known_secrets=("token-secret",))
    with pytest.raises(ValueError):
        build_normalized_state({"token-secret": "safe"}, known_secrets=("token-secret",))
    with pytest.raises(ValueError):
        parse_observer_json(
            b'{"schema_version":"2","canonical_data":{"token-secret":"safe"},"canonical_sha256":"' + observer_canonical_sha256({"token-secret": "safe"}).encode() + b'","byte_count":23}',
            NormalizedState,
            known_secrets=("token-secret",),
        )
    state = build_normalized_state({"b": 2, "a": 1})
    assert state.canonical_data == {"a": 1, "b": 2}
