from __future__ import annotations

import http.client
import json
import os
import sys
import threading
from pathlib import Path
from urllib.parse import quote

import pytest

from tests.verification.permission_test_target import create_complex_permission_test_server
from product.protocols import (
    AsyncTaskApiLocator,
    AsyncTaskPollBudget,
    AuditLogScanBudget,
    Correlation,
    ObservationCompleteness,
    ObservationPhase,
    ObserverBudget,
    ObserverOutcomeStatus,
    ObserverSpec,
    ObserverTarget,
    ObserverType,
    SqliteQueryLocator,
    StructuredAuditLogLocator,
)
from product.backend.infra.observers.async_task import run_async_task_observer
from product.backend.infra.observers.audit_log import run_audit_log_observer
from product.backend.infra.observers.sqlite import run_sqlite_observer


PYTHON = sys.executable
SUBJECT_TOKEN = "permission-member-a-token"
OBSERVER_TOKEN = "async-observer-token"
CASE_TAG = {
    "fixed": "case-async-fixed",
    "vulnerable": "case-async-vulnerable",
    "inconclusive": "case-async-inconclusive",
}
def _request(server, method: str, path: str, *, token: str, case_tag: str | None = None, body: dict | None = None) -> tuple[int, dict]:
    payload = b"" if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {"Authorization": f"Bearer {token}"}
    if case_tag is not None:
        headers["X-Jiejian-Case-ID"] = case_tag
    if body is not None:
        headers["Content-Type"] = "application/json"
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    try:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw) if raw else {}
    finally:
        connection.close()


def _sqlite_spec() -> ObserverSpec:
    return ObserverSpec(
        observer_id="sqlite_observer",
        observer_type=ObserverType.READ_ONLY_SQLITE,
        target=ObserverTarget(
            target_id="sample_sqlite",
            locator=SqliteQueryLocator(query_template_id="resource-state", table_or_view="resource_state", database_secret_ref="env:ASYNC_DB"),
            normalization_id="resource_state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.BEFORE, ObservationPhase.AFTER),
        required=True,
        budget=ObserverBudget(timeout_us=5_000_000, max_rows=32, max_bytes=65_536),
    )


def _audit_spec() -> ObserverSpec:
    return ObserverSpec(
        observer_id="audit_observer",
        observer_type=ObserverType.STRUCTURED_AUDIT_LOG,
        target=ObserverTarget(
            target_id="sample_audit",
            locator=StructuredAuditLogLocator(
                authorized_root_ref="env:ASYNC_AUDIT_ROOT",
                relative_file_pattern="audit.jsonl",
                allowed_fields=("event_id", "case_tag", "task_id", "event_type", "sequence", "resource_id", "terminal_state", "result", "effect", "value"),
                scan_budget=AuditLogScanBudget(max_files=1, max_lines=32, max_line_bytes=2048),
            ),
            normalization_id="audit_window",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.AFTER,),
        required=True,
        budget=ObserverBudget(timeout_us=5_000_000, max_rows=32, max_bytes=65_536),
    )


def _async_spec(server) -> ObserverSpec:
    return ObserverSpec(
        observer_id="task_observer",
        observer_type=ObserverType.ASYNC_TASK_STATUS,
        target=ObserverTarget(
            target_id="sample_task_api",
            locator=AsyncTaskApiLocator(
                base_url=f"http://127.0.0.1:{server.server_port}",
                relative_path_template="/observer/tasks/document-b/by-case/{request_marker}",
                read_only_credential_ref="env:ASYNC_OBSERVER_TOKEN",
                allow_private_network=True,
                allow_loopback_http=True,
                poll_budget=AsyncTaskPollBudget(max_polls=8, poll_interval_us=5_000, per_request_timeout_us=500_000, max_response_bytes=4096),
            ),
            normalization_id="async_task_state",
            normalization_version="1.0",
        ),
        phases=(ObservationPhase.EVENTUAL,),
        required=True,
        budget=ObserverBudget(timeout_us=5_000_000, max_rows=1, max_bytes=16_384),
    )


def _state(result):
    assert result.envelope is not None
    assert result.envelope.state is not None
    return result.envelope.state.canonical_data


def _row(state: dict, resource_id: str) -> dict:
    return next(row for row in state["rows"] if row["resource_id"] == resource_id)


@pytest.mark.parametrize("variant", ("fixed", "vulnerable", "inconclusive"))
def test_async_causal_facets_are_separate_and_deterministic(tmp_path: Path, variant: str) -> None:
    database_path = tmp_path / "target.db"
    audit_root = tmp_path / "audit"
    server = create_complex_permission_test_server(
        variant=variant,
        port=0,
        database_path=database_path,
        audit_root=audit_root,
        observer_token=OBSERVER_TOKEN,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    case_tag = CASE_TAG[variant]
    correlation = Correlation(case_id=case_tag, resource_id="document-b", request_marker=case_tag)
    try:
        child_environment = {
            **os.environ,
            "SSL_CERT_FILE": os.environ.get("SSL_CERT_FILE", ""),
            "SSL_CERT_DIR": os.environ.get("SSL_CERT_DIR", ""),
        }
        before = run_sqlite_observer(_sqlite_spec(), correlation, ObservationPhase.BEFORE, attempt_dir=tmp_path / "before", parent_environ={**child_environment, "ASYNC_DB": str(database_path)}, python_executable=PYTHON)
        assert before.outcome.status is ObserverOutcomeStatus.AVAILABLE
        status, _ = _request(server, "POST", "/resources/document-b/async-modify", token=SUBJECT_TOKEN, case_tag=case_tag, body={"value": f"async-{variant}"})
        assert status == 403
        task = run_async_task_observer(_async_spec(server), correlation, ObservationPhase.EVENTUAL, attempt_dir=tmp_path / "task", parent_environ={**child_environment, "ASYNC_OBSERVER_TOKEN": OBSERVER_TOKEN}, python_executable=PYTHON)
        audit = run_audit_log_observer(_audit_spec(), correlation, ObservationPhase.AFTER, attempt_dir=tmp_path / "audit-observer", parent_environ={**child_environment, "ASYNC_AUDIT_ROOT": str(audit_root)}, python_executable=PYTHON)
        after = run_sqlite_observer(_sqlite_spec(), correlation, ObservationPhase.AFTER, attempt_dir=tmp_path / "after", parent_environ={**child_environment, "ASYNC_DB": str(database_path)}, python_executable=PYTHON)
        assert audit.outcome.status is ObserverOutcomeStatus.AVAILABLE
        assert audit.envelope is not None and audit.envelope.completeness is ObservationCompleteness.COMPLETE
        assert after.outcome.status is ObserverOutcomeStatus.AVAILABLE
        before_state = _state(before)
        after_state = _state(after)
        task_state = None if task.envelope is None or task.envelope.state is None else _state(task)
        audit_state = _state(audit)
        facets = {
            "http": {"method": "POST", "status": status, "resource_id": "document-b"},
            "audit_log": {"outcome": audit.outcome.status.value, "state": audit_state},
            "async_task": {"outcome": task.outcome.status.value, "state": task_state, "reason_codes": list(task.outcome.reason_codes)},
            "final_side_effect": {"before": before_state, "after": after_state},
        }
        assert set(facets) == {"http", "audit_log", "async_task", "final_side_effect"}
        serialized = json.dumps(facets, sort_keys=True)
        assert SUBJECT_TOKEN not in serialized
        assert OBSERVER_TOKEN not in serialized
        assert str(tmp_path) not in serialized
        assert correlation.request_marker == case_tag
        assert task.envelope is not None and task.envelope.correlation.request_marker == case_tag
        assert audit.envelope is not None and audit.envelope.correlation.request_marker == case_tag
        assert _row(before_state, "document-b")["value"] == "b-initial"
        if variant == "fixed":
            assert task.outcome.status is ObserverOutcomeStatus.AVAILABLE
            assert task_state["task_state"] == "NOT_CREATED"
            assert _row(after_state, "document-b")["value"] == "b-initial"
            assert facets["final_side_effect"]["before"] == facets["final_side_effect"]["after"]
            assert [record["event_type"] for record in audit_state["records"]] == ["REQUEST"]
            assert [record["sequence"] for record in audit_state["records"]] == [1]
            assert [record["task_id"] for record in audit_state["records"]] == [""]
            assert facets["http"]["status"] == 403
        elif variant == "vulnerable":
            assert task.outcome.status is ObserverOutcomeStatus.AVAILABLE
            assert task_state["task_state"] == "SUCCESS"
            task_id = task_state["task_id"]
            assert task_id and audit_state["records"][0]["task_id"] == ""
            assert all(record["task_id"] == task_id for record in audit_state["records"][1:])
            assert [record["event_type"] for record in audit_state["records"]] == ["REQUEST", "TASK_STATE", "TASK_STATE", "SIDE_EFFECT", "TASK_STATE"]
            assert [record["sequence"] for record in audit_state["records"]] == [1, 2, 3, 4, 5]
            assert audit_state["records"][3]["effect"] == "APPLIED"
            assert audit_state["records"][-1]["terminal_state"] == audit_state["records"][-1]["result"] == "SUCCESS"
            assert task_state["final_result"] == {"effect": "APPLIED"}
            assert _row(after_state, "document-b")["value"] == "async-vulnerable"
            assert _row(before_state, "document-b") != _row(after_state, "document-b")
        else:
            assert task.outcome.status is ObserverOutcomeStatus.INCONCLUSIVE
            assert task.envelope is not None and task.envelope.completeness is ObservationCompleteness.PARTIAL
            assert [record["event_type"] for record in audit_state["records"]] == ["REQUEST", "TASK_STATE", "TASK_STATE", "SIDE_EFFECT", "TASK_STATE"]
            assert [record["sequence"] for record in audit_state["records"]] == [1, 2, 3, 4, 5]
            assert len({record["task_id"] for record in audit_state["records"][1:]}) == 1
            assert audit_state["records"][3]["effect"] == "APPLIED"
            assert audit_state["records"][-1]["terminal_state"] == audit_state["records"][-1]["result"] == "SUCCESS"
            assert _row(after_state, "document-b")["value"] == "async-inconclusive"
            assert _row(before_state, "document-b") != _row(after_state, "document-b")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_async_action_rejects_bad_tags_wrong_observer_and_is_idempotent(tmp_path: Path) -> None:
    server = create_complex_permission_test_server(variant="vulnerable", port=0, audit_root=tmp_path / "audit", observer_token=OBSERVER_TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _request(server, "POST", "/resources/document-b/async-modify", token=SUBJECT_TOKEN, body={"value": "x"})[0] == 400
        assert _request(server, "POST", "/resources/document-b/async-modify", token=SUBJECT_TOKEN, case_tag="bad/tag", body={"value": "x"})[0] == 400
        assert _request(server, "GET", "/observer/tasks/document-b/by-case/case-async-wrong", token="wrong-token")[0] == 401
        path = "/resources/document-b/async-modify"
        assert _request(server, "POST", path, token=SUBJECT_TOKEN, case_tag="case-async-idempotent", body={"value": "x"})[0] == 403
        assert _request(server, "POST", path, token=SUBJECT_TOKEN, case_tag="case-async-idempotent", body={"value": "y"})[0] == 403
        records = (tmp_path / "audit" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        assert sum(json.loads(line)["event_type"] == "REQUEST" for line in records) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


@pytest.mark.parametrize("secret_value", [SUBJECT_TOKEN, OBSERVER_TOKEN])
def test_async_observation_never_echoes_user_value_secret(tmp_path: Path, secret_value: str) -> None:
    database_path = tmp_path / "target.db"
    audit_root = tmp_path / "audit"
    server = create_complex_permission_test_server(
        variant="vulnerable",
        port=0,
        database_path=database_path,
        audit_root=audit_root,
        observer_token=OBSERVER_TOKEN,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    case_tag = "case-async-secret-" + ("subject" if secret_value == SUBJECT_TOKEN else "observer")
    correlation = Correlation(case_id=case_tag, resource_id="document-b", request_marker=case_tag)
    child_environment = {**os.environ}
    try:
        status, _ = _request(server, "POST", "/resources/document-b/async-modify", token=SUBJECT_TOKEN, case_tag=case_tag, body={"value": secret_value})
        assert status == 403
        task = run_async_task_observer(
            _async_spec(server),
            correlation,
            ObservationPhase.EVENTUAL,
            attempt_dir=tmp_path / "task",
            parent_environ={**child_environment, "ASYNC_OBSERVER_TOKEN": OBSERVER_TOKEN},
            python_executable=PYTHON,
        )
        assert task.outcome.status is ObserverOutcomeStatus.AVAILABLE
        assert task.envelope is not None and task.envelope.state is not None
        assert secret_value not in task.envelope.model_dump_json()
        direct_status, direct_payload = _request(
            server,
            "GET",
            "/observer/tasks/document-b/by-case/" + quote(case_tag, safe=""),
            token=OBSERVER_TOKEN,
        )
        assert direct_status == 200
        assert secret_value not in json.dumps(direct_payload, sort_keys=True)
        audit = run_audit_log_observer(
            _audit_spec(),
            correlation,
            ObservationPhase.AFTER,
            attempt_dir=tmp_path / "audit-observer",
            parent_environ={**child_environment, "ASYNC_AUDIT_ROOT": str(audit_root)},
            python_executable=PYTHON,
        )
        assert audit.outcome.status is ObserverOutcomeStatus.AVAILABLE
        assert audit.envelope is not None
        assert secret_value not in audit.envelope.model_dump_json()
        assert secret_value not in (audit_root / "audit.jsonl").read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def test_async_task_cap_and_worker_cleanup(tmp_path: Path) -> None:
    server = create_complex_permission_test_server(variant="vulnerable", port=0, database_path=tmp_path / "target.db")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for index in range(64):
            assert _request(server, "POST", "/resources/document-b/async-modify", token=SUBJECT_TOKEN, case_tag=f"case-cap-{index}", body={"value": str(index)})[0] == 403
        assert _request(server, "POST", "/resources/document-b/async-modify", token=SUBJECT_TOKEN, case_tag="case-cap-over", body={"value": "over"})[0] == 429
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()
        assert not server._async_threads
