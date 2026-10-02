# 防止验收程序把计划身份或进程清理当作已经核实的业务事实。
from dataclasses import replace

from tests.acceptance.sample_test.validation.runtime import _identity_matches
from tests.acceptance.sample_test.validation.models import _ExecutionObservation
from product.backend.core.verification.facts import ObservedEffect


def test_planned_identity_or_missing_history_is_not_attribution():
    assert not _identity_matches([], "bob")
    assert not _identity_matches([{"kind": "ENTRY", "identity": "bob"}], "bob")
    assert not _identity_matches([{"kind": "IDENTITY", "identity": "alice"}], "bob")
    assert _identity_matches([{"kind": "IDENTITY", "identity": "bob"}], "bob")
    assert not _identity_matches([{"kind": "IDENTITY", "identity": "bob"}, {"kind": "IDENTITY", "identity": "alice"}], "bob")


def test_cleanup_cannot_promote_business_recovery():
    value = _ExecutionObservation(200, ObservedEffect.CONFIRMED, (), False, 403, ObservedEffect.UNKNOWN, (), False, False, False)
    closed = replace(value, process_cleanup_success=True)
    assert closed.process_cleanup_success
    assert not closed.recovery_success and not closed.actual_identity_attributed
