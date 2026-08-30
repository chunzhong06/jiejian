# sample-test validation 编排：运行两类真实 Web fixture，把公开事实交给界鉴判定，再由外层 private oracle 验收。

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from secrets import token_urlsafe
from threading import Thread
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.breakpoints import BreakpointLocator, BreakpointResult
from product.backend.core.verification.continuity import (
    AuthorizationContinuityState,
    assess_authorization_continuity,
)
from product.backend.core.verification.differential import TwinExecutionRole
from product.backend.core.verification.facts import (
    DisclosureProof,
    ExecutionFact,
    ExecutionOutcome,
    ObservedEffect,
    SecurityEffectFact,
    TargetType,
    TemporalClosure,
)
from product.backend.core.verification.permissions import (
    ActionDefinition,
    CoverageDimension,
    PermissionContext,
    PermissionExpectation,
    SecurityEffectKind,
)
from product.backend.core.verification.permissions.coverage import (
    PermissionMutationCase,
    RetentionReason,
)
from product.backend.core.verification.permissions.evaluation import (
    CaseDecisionInput,
    evaluate_permission_case,
)
from .adapter import build_validation_domain_bundle
from .oracle import OracleEvaluation, PrivateOracleEvaluator
from .registry import (
    PublicValidationCase,
    ValidationCaseResult,
    load_public_registry,
    public_registry_payload,
)


_VERDICT = {
    CaseVerdict.VULNERABLE: "BLOCK",
    CaseVerdict.SAFE: "PASS",
    CaseVerdict.INCONCLUSIVE: "INCONCLUSIVE",
}
OFFICIAL_PROJECT_ID = "campus-digital-museum"
OFFICIAL_RESOURCE_ID = "campus-digital-museum-package"


class ValidationSuiteError(RuntimeError):
    """只承载无 oracle 正文的稳定 suite 失败码。"""


@dataclass(frozen=True, slots=True)
class _ExecutionObservation:
    allow_status: int
    allow_effect: ObservedEffect
    allow_trace: tuple[Mapping[str, object], ...]
    allow_trace_complete: bool
    deny_status: int
    deny_effect: ObservedEffect
    deny_trace: tuple[Mapping[str, object], ...]
    deny_trace_complete: bool
    actual_identity_attributed: bool
    recovery_success: bool


def run_validation_suite(
    root: Path,
    var_dir: Path,
    *,
    repetitions: int,
    representative_only: bool = False,
) -> dict[str, object]:
    """执行公开 registry，private oracle 只决定最终退出状态。"""

    if repetitions not in {1, 3}:
        raise ValidationSuiteError("VALIDATION_REPETITIONS_INVALID")
    root = root.resolve()
    if str(root) not in sys.path:
        # samples 是仓库内验证资产而非发布包；validation suite 只在 tests 边界显式装配它。
        sys.path.insert(0, str(root))
    var_dir = var_dir.resolve()
    var_dir.mkdir(parents=True, exist_ok=True)
    if any(var_dir.iterdir()):
        raise ValidationSuiteError("VALIDATION_VAR_DIR_NOT_EMPTY")
    cases = load_public_registry(root)
    if representative_only:
        cases = _representative_cases(cases)
    public_input = public_registry_payload(root, cases)
    audit_dir = var_dir / "audit" / "sample-test"
    audit_dir.mkdir(parents=True)
    _write_json(audit_dir / "validation-public-input.json", public_input)
    evaluator = PrivateOracleEvaluator(root, cases)
    all_results: list[dict[str, object]] = []
    evaluations: list[OracleEvaluation] = []
    for repetition in range(1, repetitions + 1):
        current: list[ValidationCaseResult] = []
        for index, case in enumerate(cases, start=1):
            case_dir = var_dir / "runtime" / "validation" / f"r{repetition}" / case.case_id
            observation = _execute_case(case, case_dir)
            result = _evaluate_case(case, observation)
            current.append(result)
            all_results.append(
                {
                    "repetition": repetition,
                    **result.public_payload(),
                }
            )
            print(
                f"[validation {repetition}/{repetitions}] "
                f"{index}/{len(cases)} {case.case_id}: {result.verdict}",
                flush=True,
            )
        evaluation = evaluator.evaluate(tuple(current))
        evaluations.append(evaluation)
        full_metrics = evaluation.method_metrics["full"]
        if (
            full_metrics["wrong_pass_vulnerable"]
            or full_metrics["wrong_pass_evidence_gap"]
        ):
            _write_public_summary(
                audit_dir,
                repetitions,
                cases,
                all_results,
                evaluations,
                status="failed",
            )
            raise ValidationSuiteError("VALIDATION_SECURITY_FLOOR_FAILED")
        if evaluation.mismatch_count:
            _write_public_summary(
                audit_dir,
                repetitions,
                cases,
                all_results,
                evaluations,
                status="failed",
            )
            raise ValidationSuiteError(
                f"VALIDATION_PRIVATE_ORACLE_MISMATCH:{evaluation.mismatch_count}"
            )
    summary = _write_public_summary(
        audit_dir,
        repetitions,
        cases,
        all_results,
        evaluations,
        status="accepted",
    )
    print(
        f"validation suite 完成：{len(cases)} Case × {repetitions}。",
        flush=True,
    )
    return summary


def _representative_cases(
    cases: tuple[PublicValidationCase, ...],
) -> tuple[PublicValidationCase, ...]:
    """每个应用取同一公开模式的三态代表，不根据 private oracle 选样。"""

    applications = sorted({item.application_id for item in cases})
    selected = tuple(
        item
        for item in cases
        if item.application_id in applications
        and item.mode == "object_tenant_check_missing"
    )
    if len(selected) != len(applications) * 3:
        raise ValidationSuiteError("VALIDATION_REPRESENTATIVE_SET_INVALID")
    return selected


def _execute_case(
    case: PublicValidationCase,
    case_dir: Path,
) -> _ExecutionObservation:
    case_dir.mkdir(parents=True)
    if case.application_id == "tenant-records":
        return _run_tenant_case(case, case_dir)
    if case.application_id == "collaboration-space":
        return _run_official_case(case, case_dir)
    raise ValidationSuiteError("VALIDATION_APPLICATION_UNSUPPORTED")


def _run_tenant_case(
    case: PublicValidationCase,
    case_dir: Path,
) -> _ExecutionObservation:
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
    observation: _ExecutionObservation | None = None
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
            observation = _ExecutionObservation(
                allow_status=allow_status,
                allow_effect=allow_effect,
                allow_trace=allow_trace,
                allow_trace_complete=allow_trace_complete,
                deny_status=deny_status,
                deny_effect=deny_effect,
                deny_trace=deny_trace,
                deny_trace_complete=trace_complete,
                actual_identity_attributed=True,
                recovery_success=False,
            )
        finally:
            _stop_process(process)
    if observation is None:
        raise ValidationSuiteError("VALIDATION_TENANT_OBSERVATION_MISSING")
    return replace(observation, recovery_success=True)


def _run_official_case(
    case: PublicValidationCase,
    case_dir: Path,
) -> _ExecutionObservation:
    """直接运行现有 Official Sample 业务实现，不启动第二个产品 Sample。"""

    from samples.web.collaboration_space.source.server import (
        create_collaboration_space_server,
    )

    selector = case.state_selector
    passwords = {
        account: f"validation-{account}-{token_urlsafe(18)}"
        for account in ("alice", "bob")
    }
    sessions = {
        account: f"session-{account}-{token_urlsafe(18)}"
        for account in ("alice", "bob")
    }
    task_bearer = f"task-{token_urlsafe(24)}"
    server = create_collaboration_space_server(
        port=0,
        runtime_root=case_dir / "state",
        authorization_order="AUTHORIZE_BEFORE_ENQUEUE",
        blob_observation=str(selector.get("observation")),
        validation_mode=case.mode,
        validation_implementation=str(selector.get("implementation")),
        passwords=passwords,
        session_material=sessions,
        queue_sas="sv=validation&sig=" + token_urlsafe(24),
        blob_sas="sv=validation&sig=" + token_urlsafe(24),
        task_bearer=task_bearer,
        owner_observer=f"owner-{token_urlsafe(24)}",
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    observation: _ExecutionObservation | None = None
    try:
        allow_marker = f"{case.case_id}-allow"
        allow_status, allow_task = _official_action(
            origin,
            sessions["alice"],
            task_bearer,
            allow_marker,
        )
        allow_effect = _official_effect(selector, allow_task, allow_control=True)
        allow_trace = _official_trace(server.runtime_root, allow_marker)
        server.reset()
        deny_marker = f"{case.case_id}-deny"
        deny_status, deny_task = _official_action(
            origin,
            sessions["bob"],
            task_bearer,
            deny_marker,
        )
        deny_effect = _official_effect(selector, deny_task)
        trace = _official_trace(server.runtime_root, deny_marker)
        observation = _ExecutionObservation(
            allow_status=allow_status,
            allow_effect=allow_effect,
            allow_trace=allow_trace,
            allow_trace_complete=True,
            deny_status=deny_status,
            deny_effect=deny_effect,
            deny_trace=trace,
            deny_trace_complete=True,
            actual_identity_attributed=True,
            recovery_success=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            raise ValidationSuiteError("VALIDATION_OFFICIAL_SAMPLE_NOT_CLOSED")
    if observation is None:
        raise ValidationSuiteError("VALIDATION_OFFICIAL_OBSERVATION_MISSING")
    return replace(observation, recovery_success=True)


def _evaluate_case(
    case: PublicValidationCase,
    observation: _ExecutionObservation,
) -> ValidationCaseResult:
    """把真实 fixture 事实交给既有 Permission Verification 纯判定。"""

    allow_input = _decision_input(
        case,
        expectation=PermissionExpectation.ALLOW,
        outcome=_execution_outcome(observation.allow_status),
        effect=observation.allow_effect,
        twin_role=TwinExecutionRole.ALLOW_CONTROL,
        allow_control_valid=True,
    )
    allow_verdict, _ = evaluate_permission_case(allow_input)
    allow_valid = allow_verdict is CaseVerdict.SAFE
    deny_input = _decision_input(
        case,
        expectation=PermissionExpectation.DENY,
        outcome=_execution_outcome(observation.deny_status),
        effect=observation.deny_effect,
        twin_role=TwinExecutionRole.DENY_VARIANT,
        allow_control_valid=allow_valid,
    )
    verdict, _ = evaluate_permission_case(deny_input)
    public_verdict = _VERDICT[verdict]
    bundle = build_validation_domain_bundle(
        case,
        allow_trace_records=observation.allow_trace,
        deny_trace_records=observation.deny_trace,
        allow_trace_complete=observation.allow_trace_complete,
        deny_trace_complete=observation.deny_trace_complete,
        allow_effect_fact=_effect_fact(case, observation.allow_effect),
        deny_effect_fact=_effect_fact(case, observation.deny_effect),
    )
    continuity = assess_authorization_continuity(
        bundle.contract,
        bundle.twin,
        bundle.deny_effect_facts,
    )
    breakpoint = BreakpointLocator().locate(
        contract=bundle.contract,
        differential_plan=bundle.plan,
        allow_trace=bundle.allow_trace,
        deny_trace=bundle.deny_trace,
        allow_effect_facts=bundle.allow_effect_facts,
        deny_effect_facts=bundle.deny_effect_facts,
        evidence_refs=bundle.evidence_refs,
    )
    breakpoint_type, breakpoint_location, breakpoint_range, precision = (
        _breakpoint_projection(breakpoint, bundle.deny_trace)
    )
    continuity_label = {
        AuthorizationContinuityState.INTACT: "INTACT",
        AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED: "BROKEN",
        AuthorizationContinuityState.UNKNOWN: "UNKNOWN",
    }[continuity.state]
    orphan_effect = {
        AuthorizationContinuityState.INTACT: False,
        AuthorizationContinuityState.ORPHAN_EFFECT_CONFIRMED: True,
        AuthorizationContinuityState.UNKNOWN: None,
    }[continuity.state]
    return ValidationCaseResult(
        case_id=case.case_id,
        application_id=case.application_id,
        mode=case.mode,
        verdict=public_verdict,
        allow_control_valid=allow_valid,
        breakpoint_type=breakpoint_type,
        breakpoint_location=breakpoint_location,
        breakpoint_range=breakpoint_range,
        precision=precision,
        effect_state=observation.deny_effect.value,
        authorization_continuity=continuity_label,
        orphan_effect_detected=orphan_effect,
        actual_identity_attributed=observation.actual_identity_attributed,
        recovery_success=observation.recovery_success,
        baseline_verdicts=_baseline_verdicts(observation),
    )


def _breakpoint_projection(
    breakpoint: BreakpointResult | None,
    deny_trace,
) -> tuple[str | None, str | None, tuple[str, ...], str | None]:
    """把生产 Locator 的事件引用投影成既有公开 validation 摘要。"""

    if breakpoint is None:
        return None, None, (), None
    events = {item.event_id: item for item in deny_trace.events}
    location = (
        events[breakpoint.first_violation_event_id].semantic_key
        if breakpoint.first_violation_event_id is not None
        else None
    )
    range_keys = tuple(
        events[event_id].semantic_key
        for event_id in (
            breakpoint.range_start_event_id,
            breakpoint.range_end_event_id,
        )
        if event_id is not None
    )
    return (
        breakpoint.breakpoint_type.value if breakpoint.breakpoint_type is not None else None,
        location,
        range_keys,
        breakpoint.precision.value,
    )


def _baseline_verdicts(
    observation: _ExecutionObservation,
) -> Mapping[str, str]:
    """按公开执行事实运行三种受限基线，不复用完整判定结果。"""

    http_only = "BLOCK" if 200 <= observation.deny_status < 300 else "PASS"
    single_state = {
        ObservedEffect.CONFIRMED: "BLOCK",
        ObservedEffect.ABSENT: "PASS",
        ObservedEffect.UNKNOWN: "INCONCLUSIVE",
    }[observation.deny_effect]
    allow_accepted = 200 <= observation.allow_status < 300
    if 200 <= observation.deny_status < 300:
        authorization_regression = "BLOCK"
    elif observation.deny_status in {401, 403} and allow_accepted:
        authorization_regression = "PASS"
    else:
        authorization_regression = "INCONCLUSIVE"
    return {
        "http_only": http_only,
        "single_state": single_state,
        "authorization_regression": authorization_regression,
    }


def _decision_input(
    case: PublicValidationCase,
    *,
    expectation: PermissionExpectation,
    outcome: ExecutionOutcome,
    effect: ObservedEffect,
    twin_role: TwinExecutionRole,
    allow_control_valid: bool,
) -> CaseDecisionInput:
    digest = hashlib.sha256(case.case_id.encode("utf-8")).hexdigest()
    case_id = "case-" + digest[:32]
    mutation = PermissionMutationCase(
        case_id=case_id,
        fingerprint=digest,
        finding_pre_identity=hashlib.sha256((case.case_id + "|finding").encode()).hexdigest(),
        source_rule_ids=("validation-public-intent",),
        dimensions=(CoverageDimension.RELATION,),
        retention_reason=RetentionReason.EXPLICIT_DENY_RISK,
        subject_id=case.allow_control_identity if expectation is PermissionExpectation.ALLOW else case.identity,
        action_id=case.business_action,
        resource_ids=(case.resource,),
        expectations=(expectation,),
        relation_paths=((str(case.permission_intent.get("relation") or "relation").casefold(),),),
        context=PermissionContext(
            tenant_ids=("tenant-alpha",),
            resource_ids=(case.resource,),
        ),
        required_observations=(str(case.observation_config.get("required_channel")),),
    )
    execution = ExecutionFact(
        case_id=case_id,
        action_id=case.business_action,
        target_type=TargetType.WEB,
        outcome=outcome,
        execution_marker="validation-" + digest[:20],
        input_hash=digest,
        output_hash=hashlib.sha256((case.case_id + "|" + outcome.value).encode()).hexdigest(),
        reason_codes=("VALIDATION_EXECUTION_FAILED",) if outcome is ExecutionOutcome.FAILED else (),
    )
    effect_fact = _effect_fact(case, effect)
    return CaseDecisionInput(
        case=mutation,
        action=ActionDefinition(
            action_id=case.business_action,
            effect_ids=case.protected_effects,
        ),
        execution=execution,
        effects=(effect_fact,),
        twin_role=twin_role,
        allow_control_valid=allow_control_valid,
        baseline_integrity=True,
    )


def _effect_fact(
    case: PublicValidationCase,
    state: ObservedEffect,
) -> SecurityEffectFact:
    complete = state is not ObservedEffect.UNKNOWN
    effect_kind = SecurityEffectKind(str(case.observation_config.get("effect_kind")))
    disclosure = None
    if effect_kind is SecurityEffectKind.DATA_DISCLOSURE:
        owner_digest = hashlib.sha256((case.case_id + "|owner").encode()).hexdigest()
        response_digest = (
            owner_digest
            if state is ObservedEffect.CONFIRMED
            else hashlib.sha256((case.case_id + "|response").encode()).hexdigest()
        )
        disclosure = DisclosureProof(
            projection_version="validation-v1",
            projection_complete=complete,
            owner_digest=owner_digest,
            response_digest=response_digest,
            matched=state is ObservedEffect.CONFIRMED,
            correlation_digest=hashlib.sha256((case.case_id + "|correlation").encode()).hexdigest(),
        )
    return SecurityEffectFact(
        effect_id=case.protected_effects[0],
        kind=effect_kind,
        resource_id=case.resource,
        state=state,
        complete=complete,
        reliable=complete,
        correlated=complete,
        temporal_closure=TemporalClosure.CLOSED if complete else TemporalClosure.UNKNOWN,
        baseline_integrity=True,
        source_requirement_ids=(str(case.observation_config.get("required_channel")),),
        disclosure_proof=disclosure,
        reason_codes=() if complete else ("VALIDATION_OBSERVATION_UNAVAILABLE",),
    )


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
        raise ValidationSuiteError("VALIDATION_TENANT_ACTION_UNSUPPORTED") from exc
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
            raise ValidationSuiteError("VALIDATION_TENANT_OBSERVATION_INVALID")
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
        raise ValidationSuiteError("VALIDATION_TENANT_ALLOW_LOG_UNAVAILABLE")
    events: list[Mapping[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if isinstance(value, dict) and value.get("case_id") == marker:
            events.append(value)
    return tuple(events)


def _official_action(
    origin: str,
    session: str,
    task_bearer: str,
    marker: str,
) -> tuple[int, Mapping[str, object]]:
    status, _ = _http_json(
        origin,
        "POST",
        f"/api/projects/{OFFICIAL_PROJECT_ID}/exports",
        {"resource_id": OFFICIAL_RESOURCE_ID},
        headers={
            "Cookie": f"jiejian_sample_session={session}",
            "X-Jiejian-Case-ID": marker,
        },
        accepted=(202, 403),
    )
    deadline = time.monotonic() + 5
    task: Mapping[str, object] | None = None
    while time.monotonic() < deadline:
        task_status, payload = _http_json(
            origin,
            "GET",
            f"/api/tasks/{marker}",
            headers={"Authorization": f"Bearer {task_bearer}"},
            accepted=(200,),
        )
        if task_status == 200 and isinstance(payload, dict):
            task = payload
            if task.get("state") in {"SUCCESS", "FAILED", "NOT_CREATED", "REVOKED"}:
                return status, task
        time.sleep(0.02)
    raise ValidationSuiteError("VALIDATION_OFFICIAL_TASK_TIMEOUT")


def _official_effect(
    selector: Mapping[str, object],
    task: Mapping[str, object],
    *,
    allow_control: bool = False,
) -> ObservedEffect:
    if selector.get("observation") == "UNAVAILABLE" and not allow_control:
        return ObservedEffect.UNKNOWN
    return (
        ObservedEffect.CONFIRMED
        if task.get("state") == "SUCCESS"
        else ObservedEffect.ABSENT
    )


def _official_trace(
    runtime_root: Path,
    marker: str,
) -> tuple[Mapping[str, object], ...]:
    path = runtime_root / "audit" / "events.jsonl"
    if not path.is_file():
        return ()
    records: list[Mapping[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if isinstance(value, dict) and value.get("case_tag") == marker:
            records.append(value)
    return tuple(records)


def _execution_outcome(status: int) -> ExecutionOutcome:
    if 200 <= status < 300:
        return ExecutionOutcome.ACCEPTED
    if status in {401, 403}:
        return ExecutionOutcome.DENIED
    return ExecutionOutcome.FAILED


def _node_executable() -> Path:
    configured = os.environ.get("JIEJIAN_NODE_EXECUTABLE")
    candidate = Path(configured).resolve() if configured else None
    if candidate is not None and candidate.is_file():
        return candidate
    discovered = shutil.which("node.exe") or shutil.which("node")
    if discovered:
        return Path(discovered).resolve()
    raise ValidationSuiteError("VALIDATION_NODE_UNAVAILABLE")


def _wait_node_ready(
    ready_file: Path,
    process: subprocess.Popen[bytes],
) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ValidationSuiteError(
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
    raise ValidationSuiteError("VALIDATION_TENANT_APP_READY_TIMEOUT")


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if process.poll() is None:
        raise ValidationSuiteError("VALIDATION_TENANT_APP_NOT_CLOSED")


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
        raise ValidationSuiteError("VALIDATION_HTTP_UNAVAILABLE") from exc
    if status not in accepted:
        raise ValidationSuiteError(f"VALIDATION_HTTP_STATUS_UNEXPECTED:{status}")
    try:
        payload = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationSuiteError("VALIDATION_HTTP_JSON_INVALID") from exc
    if not isinstance(payload, dict):
        raise ValidationSuiteError("VALIDATION_HTTP_JSON_INVALID")
    return status, payload


def _write_public_summary(
    audit_dir: Path,
    repetitions: int,
    cases: tuple[PublicValidationCase, ...],
    results: list[dict[str, object]],
    evaluations: list[OracleEvaluation],
    *,
    status: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1",
        "suite": "competition" if repetitions == 3 else "validation",
        "status": status,
        "repetitions": repetitions,
        "case_count": len(cases),
        "case_run_count": len(results),
        "applications": sorted({item.application_id for item in cases}),
        "full_method_sources": {
            "case_verdict": (
                "product.backend.core.verification.permissions.evaluation."
                "evaluate_permission_case"
            ),
            "authorization_continuity": (
                "product.backend.core.verification.continuity."
                "assess_authorization_continuity"
            ),
            "breakpoint": (
                "product.backend.core.verification.breakpoints."
                "BreakpointLocator.locate"
            ),
        },
        "method_metrics": _aggregate_method_metrics(evaluations),
        "repeat_consistency": _repeat_consistency(results),
        "results": results,
    }
    _write_json(audit_dir / "validation-summary.json", payload)
    return payload


def _aggregate_method_metrics(
    evaluations: list[OracleEvaluation],
) -> dict[str, dict[str, int]]:
    aggregate: dict[str, dict[str, int]] = {}
    for evaluation in evaluations:
        for method, metrics in evaluation.method_metrics.items():
            target = aggregate.setdefault(method, {})
            for name, value in metrics.items():
                target[name] = target.get(name, 0) + int(value)
    return aggregate


def _repeat_consistency(results: list[dict[str, object]]) -> dict[str, int]:
    signatures: dict[str, set[str]] = {}
    for result in results:
        case_id = str(result.get("case_id"))
        public_result = {key: value for key, value in result.items() if key != "repetition"}
        signatures.setdefault(case_id, set()).add(
            json.dumps(public_result, ensure_ascii=False, sort_keys=True)
        )
    consistent = sum(len(items) == 1 for items in signatures.values())
    return {
        "case_count": len(signatures),
        "consistent_case_count": consistent,
        "inconsistent_case_count": len(signatures) - consistent,
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


__all__ = ["ValidationSuiteError", "run_validation_suite"]
