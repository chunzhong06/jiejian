# 验证观察器基础设施中的SQL 跟踪建议。

from __future__ import annotations

from product.backend.core.verification.permissions import SecurityEffectKind
from product.backend.infra.observers.sql_trace import build_sql_trace_advisory


def test_sql_trace_is_redacted_advisory_without_verdict_authority() -> None:
    advisory = build_sql_trace_advisory(
        (
            "SELECT value FROM documents WHERE token = 'secret-value'",
            "INSERT INTO audit_events(id, value) VALUES (42, 'secret-value')",
            "UPDATE documents SET value = 'secret-value' WHERE id = 42",
        )
    )
    assert advisory.verdict_authority is False
    assert set(advisory.effect_suggestions) == {
        SecurityEffectKind.OBJECT_CREATION,
        SecurityEffectKind.STATE_MUTATION,
    }
    assert advisory.contract_drift_subjects == ("audit_events", "documents")
    assert advisory.observer_suggestions == ("read_only_database",)
    assert "secret-value" not in advisory.model_dump_json()
    assert not hasattr(advisory, "verdict")
