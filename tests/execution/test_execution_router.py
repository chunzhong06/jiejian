from __future__ import annotations

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.verification.facts import ExecutionOutcome, TargetType
from product.backend.infra.execution.http import HttpExecutionAdapter, HttpResponse
from product.backend.infra.execution.router import ExecutionRouter
from product.protocols import ActionExecutionBinding, ResourceInjection, WebTargetDefinition, WebTargetScope


def _binding() -> ActionExecutionBinding:
    return ActionExecutionBinding(action_id="view", target_type=TargetType.WEB, method="GET", relative_path_template="/resources/{resource_id}", accepted_statuses=(200,), denied_statuses=(401, 403, 404), resource_injection=ResourceInjection.PATH_RESOURCE_ID)


def _adapter(monkeypatch, status: int | None = 200) -> HttpExecutionAdapter:
    target = WebTargetDefinition(scope=WebTargetScope(base_url="http://127.0.0.1:8765", allowed_origins=("http://127.0.0.1:8765",), allowed_hosts=("127.0.0.1",), allowed_ports=(8765,), allow_private_network=True, timeout_seconds=5, max_requests=8, max_response_bytes=262_144), reset_path="/reset")
    adapter = HttpExecutionAdapter(target)
    if status is None:
        def fail(*_args, **_kwargs):
            raise JiejianError(ErrorCode.EXEC_TIMEOUT, "timeout")
        monkeypatch.setattr(adapter, "request", fail)
    else:
        monkeypatch.setattr(adapter, "request", lambda *_args, **_kwargs: HttpResponse(status_code=status, data={"ok": True}))
    return adapter


@pytest.mark.parametrize(("status", "expected"), [(200, ExecutionOutcome.ACCEPTED), (403, ExecutionOutcome.DENIED), (418, ExecutionOutcome.UNKNOWN)])
def test_http_adapter_reduces_status_to_target_neutral_fact(monkeypatch, status: int, expected: ExecutionOutcome) -> None:
    adapter = _adapter(monkeypatch, status)
    try:
        fact = adapter.execute(_binding(), case_id="case-" + "a" * 32, action_id="view")
        assert fact.outcome is expected
        assert "status_code" not in fact.model_dump()
    finally:
        adapter.close()


def test_http_transport_failure_is_failed_with_empty_output_hash(monkeypatch) -> None:
    adapter = _adapter(monkeypatch, None)
    try:
        fact = adapter.execute(_binding(), case_id="case-" + "a" * 32, action_id="view")
        assert fact.outcome is ExecutionOutcome.FAILED
        assert fact.output_hash == __import__("hashlib").sha256(b"").hexdigest()
    finally:
        adapter.close()


def test_router_fails_closed_for_unregistered_target_type(monkeypatch) -> None:
    adapter = _adapter(monkeypatch)
    router = ExecutionRouter((adapter,))
    try:
        with pytest.raises(JiejianError):
            router.execute(TargetType.CLI_APPLICATION, _binding(), case_id="case-" + "a" * 32, action_id="view")
    finally:
        adapter.close()


def test_router_rejects_duplicate_target_registration(monkeypatch) -> None:
    adapter = _adapter(monkeypatch)
    router = ExecutionRouter((adapter,))
    try:
        with pytest.raises(ValueError, match="already registered"):
            router.register(adapter)
    finally:
        adapter.close()
