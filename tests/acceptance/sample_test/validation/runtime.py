# 隔离跨应用目标并取得真实观察，负责目标退出。
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from product.backend.core.verification.facts import ObservedEffect
from tests.acceptance.sample_test.registry import PublicValidationCase
import tests.acceptance.sample_test.validation.models as sample_validation_models


def _execute_case(
    case: PublicValidationCase,
    case_dir: Path,
) -> sample_validation_models._ExecutionObservation:
    case_dir.mkdir(parents=True)
    if case.application_id == "tenant-records":
        return _run_tenant_case(case, case_dir)
    raise sample_validation_models.ValidationSuiteError("VALIDATION_APPLICATION_UNSUPPORTED")


def _run_tenant_case(
    case: PublicValidationCase,
    case_dir: Path,
) -> sample_validation_models._ExecutionObservation:
    """复制授权源码到运行目录，用受控 Node 进程执行 owner/member 孪生。"""

    node = _node_executable()
    runtime_source = case_dir / "source"
    shutil.copytree(case.source_root, runtime_source)
    state_dir = case_dir / "state"
    state_dir.mkdir()
    ready_file = case_dir / "ready.json"
    log_path = case_dir / "tenant-records.log"
    selector = case.state_selector
    command = [
        str(node),
        str(runtime_source / "tenant_records_app.mjs"),
        f"--state-dir={state_dir}",
        f"--ready-file={ready_file}",
        f"--mode={case.mode}",
        f"--implementation={selector.get('implementation')}",
        f"--observation={selector.get('observation')}",
    ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    observation: sample_validation_models._ExecutionObservation | None = None
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            cwd=runtime_source,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            origin = _wait_node_ready(ready_file, process)
            _, initial_state = _http_json(origin, "GET", "/_validation/state", accepted=(200,))
            allow_marker = f"{case.case_id}-allow"
            allow_status = _tenant_action(
                origin,
                case,
                identity=case.allow_control_identity,
                marker=allow_marker,
            )
            allow_effect, allow_trace, allow_trace_complete = _tenant_observation(
                origin,
                allow_marker,
                case.protected_effects,
                fallback_log=state_dir / "events.jsonl",
            )
            _http_json(origin, "POST", "/_validation/reset", accepted=(200,))
            deny_marker = f"{case.case_id}-deny"
            deny_status = _tenant_action(
                origin,
                case,
                identity=case.identity,
                marker=deny_marker,
            )
            deny_effect, deny_trace, trace_complete = _tenant_observation(
                origin,
                deny_marker,
                case.protected_effects,
            )
            observation = sample_validation_models._ExecutionObservation(
                allow_status=allow_status,
                allow_effect=allow_effect,
                allow_trace=allow_trace,
                allow_trace_complete=allow_trace_complete,
                deny_status=deny_status,
                deny_effect=deny_effect,
                deny_trace=deny_trace,
                deny_trace_complete=trace_complete,
                actual_identity_attributed=_identity_matches(allow_trace, case.allow_control_identity) and _identity_matches(
                    _tenant_events_from_log(state_dir / "events.jsonl", deny_marker), case.identity),
                recovery_success=False,
            )
            _http_json(origin, "POST", "/_validation/reset", accepted=(200,))
            _, restored_state = _http_json(origin, "GET", "/_validation/state", accepted=(200,))
            observation = replace(observation, recovery_success=restored_state == initial_state)
        finally:
            _stop_process(process)
    if observation is None:
        raise sample_validation_models.ValidationSuiteError("VALIDATION_TENANT_OBSERVATION_MISSING")
    return replace(observation, process_cleanup_success=True)



def _identity_matches(records, expected: str) -> bool:
    identities = {item.get("subject_id", item.get("identity")) for item in records if item.get("kind") == "IDENTITY"}
    return identities == {expected}



def _tenant_action(
    origin: str,
    case: PublicValidationCase,
    *,
    identity: str,
    marker: str,
) -> int:
    actions = {
        "read_record": (
            "GET",
            "/api/projects/project-alpha/records/record-owner",
            None,
        ),
        "modify_record": (
            "PATCH",
            "/api/projects/project-alpha/records/record-owner",
            {"title": "验证后的记录"},
        ),
        "grant_authority": (
            "POST",
            "/api/projects/project-alpha/members",
            {"member_id": "invited-member"},
        ),
    }
    try:
        method, path, body = actions[case.business_action]
    except KeyError as exc:
        raise sample_validation_models.ValidationSuiteError("VALIDATION_TENANT_ACTION_UNSUPPORTED") from exc
    if case.mode == "new_entry_inheritance" and case.business_action == "modify_record":
        path = "/api/projects/project-alpha/records/record-new"
    status, _ = _http_json(
        origin,
        method,
        path,
        body,
        headers={
            "X-Validation-Identity": identity,
            "X-Validation-Case-ID": marker,
        },
        accepted=(200, 403),
    )
    return status


def _tenant_observation(
    origin: str,
    marker: str,
    effects: tuple[str, ...],
    *,
    fallback_log: Path | None = None,
) -> tuple[ObservedEffect, tuple[Mapping[str, object], ...], bool]:
    deadline = time.monotonic() + 0.5
    events: list[Mapping[str, object]] = []
    while True:
        status, payload = _http_json(
            origin,
            "GET",
            f"/_validation/observations?case_id={marker}",
            accepted=(200, 503),
        )
        if status == 503:
            if fallback_log is not None:
                events = _tenant_events_from_log(fallback_log, marker)
                state = (
                    ObservedEffect.CONFIRMED
                    if any(item.get("semantic_key") in effects for item in events)
                    else ObservedEffect.ABSENT
                )
                return state, events, True
            return ObservedEffect.UNKNOWN, (), False
        raw_events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(raw_events, list) or any(not isinstance(item, dict) for item in raw_events):
            raise sample_validation_models.ValidationSuiteError("VALIDATION_TENANT_OBSERVATION_INVALID")
        events = raw_events
        if any(item.get("semantic_key") in effects for item in events):
            return ObservedEffect.CONFIRMED, tuple(events), True
        async_dispatched = any(
            item.get("semantic_key") == "denied_work_dispatched" for item in events
        )
        if not async_dispatched or time.monotonic() >= deadline:
            return ObservedEffect.ABSENT, tuple(events), True
        time.sleep(0.02)


def _tenant_events_from_log(
    path: Path,
    marker: str,
) -> tuple[Mapping[str, object], ...]:
    """ALLOW 对照使用 fixture 本地效果日志，避免 DENY 证据缺口污染控制组。"""

    if not path.is_file():
        raise sample_validation_models.ValidationSuiteError("VALIDATION_TENANT_ALLOW_LOG_UNAVAILABLE")
    events: list[Mapping[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if isinstance(value, dict) and value.get("case_id") == marker:
            events.append(value)
    return tuple(events)





def _node_executable() -> Path:
    configured = os.environ.get("JIEJIAN_NODE_EXECUTABLE")
    candidate = Path(configured).resolve() if configured else None
    if candidate is not None and candidate.is_file():
        return candidate
    discovered = shutil.which("node.exe") or shutil.which("node")
    if discovered:
        return Path(discovered).resolve()
    raise sample_validation_models.ValidationSuiteError("VALIDATION_NODE_UNAVAILABLE")


def _wait_node_ready(
    ready_file: Path,
    process: subprocess.Popen[bytes],
) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise sample_validation_models.ValidationSuiteError(
                f"VALIDATION_TENANT_APP_EXITED:{process.returncode}"
            )
        if ready_file.is_file():
            try:
                payload = json.loads(ready_file.read_text(encoding="utf-8"))
                port = int(payload["port"])
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                time.sleep(0.05)
                continue
            return f"http://127.0.0.1:{port}"
        time.sleep(0.05)
    raise sample_validation_models.ValidationSuiteError("VALIDATION_TENANT_APP_READY_TIMEOUT")


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.poll() is None:
        raise sample_validation_models.ValidationSuiteError("VALIDATION_TENANT_APP_NOT_CLOSED")


def _http_json(
    origin: str,
    method: str,
    path: str,
    body: Mapping[str, object] | None = None,
    *,
    headers: Mapping[str, str] | None = None,
    accepted: tuple[int, ...],
) -> tuple[int, Mapping[str, object]]:
    encoded = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if encoded is not None:
        request_headers["Content-Type"] = "application/json"
    request = Request(
        origin + path,
        data=encoded,
        headers=request_headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=5) as response:
            status = response.status
            raw = response.read()
    except HTTPError as exc:
        status = exc.code
        raw = exc.read()
    except (OSError, URLError) as exc:
        raise sample_validation_models.ValidationSuiteError("VALIDATION_HTTP_UNAVAILABLE") from exc
    if status not in accepted:
        raise sample_validation_models.ValidationSuiteError(f"VALIDATION_HTTP_STATUS_UNEXPECTED:{status}")
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise sample_validation_models.ValidationSuiteError("VALIDATION_HTTP_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise sample_validation_models.ValidationSuiteError("VALIDATION_HTTP_JSON_INVALID")
    return status, payload
