# =============================================================================
# Runner V2 进程内编排与 Evidence 生产
#
# 只负责冻结输入后的时序、观察器调度、纯事实投影和 staging 工件；
# HTTP 仍由 HttpExecutor 执行，最终 case 判定仍由 Verification V2 负责。
# =============================================================================

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from ..domain.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from ..errors import ErrorCode, JiejianError
from ..protocols import (
    AuditLogStartCursorV2,
    CausalityStatus,
    CleanupResultV2,
    CleanupStatusV2,
    CorrelationV2,
    EvidenceV2,
    ObservationCompleteness,
    ObservationEnvelopeV2,
    ObservationPhase,
    ObserverOutcomeStatus,
    ObserverOutcomeV2,
    ObserverSpecV2,
    ObserverType,
    ProvenanceType,
    RequestFactV2,
    RunnerErrorV2,
    RunnerInputV2,
    RunnerResultTypeV2,
    RunnerResultV2,
    StagedArtifactV2,
    build_evidence_v2,
    build_normalized_state,
    canonical_runner_v2_json_bytes,
    canonical_runner_v2_sha256,
    evaluate_observer_outcome,
    parse_runner_input_v2,
    required_secret_refs_v2,
)
from ..verification.evaluation_v2 import (
    CaseDecisionInput,
    DecisionPhaseV2,
    ObservationDecisionFact,
    ObserverKindV2,
    RequestDecisionFact,
    evaluate_permission_case_v2,
)
from ..verification.http import HttpExecutor, HttpResponse
from ..verification.owner_api_observer import OwnerApiObserverV2Adapter
from ..verification.safety import TargetGuard
from .async_task_observer import run_async_task_observer
from .audit_log_observer import run_audit_log_observer
from .blob_observer import run_azure_blob_observer
from .queue_observer import run_azure_queue_observer
from .sqlite_observer import run_sqlite_observer


RUNNER_EXIT_OK = 0
RUNNER_EXIT_PROTOCOL = 64
RUNNER_EXIT_INTERNAL = 70
RUNNER_EXIT_WRITE = 74

_PHASE_ORDER = {
    ObservationPhase.BEFORE: 0,
    ObservationPhase.AFTER: 1,
    ObservationPhase.EVENTUAL: 2,
}
_OBSERVER_KIND = {item.value: item for item in ObserverKindV2}
_V2_INCONCLUSIVE = "V2_REQUIRED_OBSERVER_INCOMPLETE"
_V2_REQUEST_FAILED = "V2_REQUEST_FAILED"
_V2_CLEANUP_FAILED = "V2_CLEANUP_FAILED"


def _now_us() -> int:
    return time.time_ns() // 1_000


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _secret_value(environ: Mapping[str, str], reference: str, *, required: bool) -> str | None:
    name = reference.removeprefix("env:")
    value = environ.get(name)
    if not value and required:
        raise JiejianError(ErrorCode.SECRET_MISSING, "执行所需秘密不可用")
    return value or None


def _failure_request(case_id: str, subject_id: str, method: str, path: str, body: Mapping[str, Any], code: str) -> RequestFactV2:
    request_payload = {"method": method, "relative_path": path, "subject_id": subject_id, "json_body": body}
    return RequestFactV2(
        method=method,
        relative_path=path,
        status_code=None,
        failure_code=code,
        request_marker=case_id,
        request_sha256=_sha256(request_payload),
        response_sha256=hashlib.sha256(b"").hexdigest(),
        request_byte_count=len(_json_bytes(request_payload)),
        response_byte_count=0,
    )


def _request_fact(case_id: str, subject_id: str, method: str, path: str, body: Mapping[str, Any], response: HttpResponse | None, failure_code: str | None = None) -> RequestFactV2:
    request_payload = {"method": method, "relative_path": path, "subject_id": subject_id, "json_body": body}
    request_bytes = _json_bytes(request_payload)
    if response is None:
        return RequestFactV2(
            method=method,
            relative_path=path,
            status_code=None,
            failure_code=failure_code or _V2_REQUEST_FAILED,
            request_marker=case_id,
            request_sha256=hashlib.sha256(request_bytes).hexdigest(),
            response_sha256=hashlib.sha256(b"").hexdigest(),
            request_byte_count=len(request_bytes),
            response_byte_count=0,
        )
    response_bytes = _json_bytes({"status_code": response.status_code, "data": response.data})
    return RequestFactV2(
        method=method,
        relative_path=path,
        status_code=response.status_code,
        failure_code=None,
        request_marker=case_id,
        request_sha256=hashlib.sha256(request_bytes).hexdigest(),
        response_sha256=hashlib.sha256(response_bytes).hexdigest(),
        request_byte_count=len(request_bytes),
        response_byte_count=len(response_bytes),
    )


def _failure_outcome(spec: ObserverSpecV2, code: str = _V2_INCONCLUSIVE) -> ObserverOutcomeV2:
    return ObserverOutcomeV2(
        observer_id=spec.observer_id,
        required=spec.required,
        status=ObserverOutcomeStatus.INCONCLUSIVE,
        reason_codes=(code,),
    )


def _aggregate_outcome(current: ObserverOutcomeV2 | None, incoming: ObserverOutcomeV2) -> ObserverOutcomeV2:
    if current is None:
        return incoming
    statuses = {current.status, incoming.status}
    status = ObserverOutcomeStatus.EXECUTION_ERROR if ObserverOutcomeStatus.EXECUTION_ERROR in statuses else ObserverOutcomeStatus.INCONCLUSIVE if ObserverOutcomeStatus.INCONCLUSIVE in statuses else ObserverOutcomeStatus.AVAILABLE
    return ObserverOutcomeV2(
        observer_id=current.observer_id,
        required=current.required,
        status=status,
        reason_codes=tuple(sorted(set((*current.reason_codes, *incoming.reason_codes)))),
    )


def _phase_for_decision(phase: ObservationPhase) -> DecisionPhaseV2:
    return DecisionPhaseV2(phase.value)


def _observer_fact(requirement_id: str, envelope: ObservationEnvelopeV2) -> ObservationDecisionFact:
    complete = envelope.completeness is ObservationCompleteness.COMPLETE and envelope.causality is CausalityStatus.CORRELATED and envelope.state is not None
    if not complete:
        return ObservationDecisionFact(
            requirement_id=requirement_id,
            observer_kind=_OBSERVER_KIND[envelope.observer_type.value],
            resource_id=envelope.correlation.resource_id,
            phase=_phase_for_decision(envelope.phase),
            available=False,
            complete=False,
            correlated=envelope.causality is CausalityStatus.CORRELATED,
        )
    return ObservationDecisionFact(
        requirement_id=requirement_id,
        observer_kind=_OBSERVER_KIND[envelope.observer_type.value],
        resource_id=envelope.correlation.resource_id,
        phase=_phase_for_decision(envelope.phase),
        available=True,
        complete=True,
        correlated=True,
        canonical_sha256=envelope.state.canonical_sha256,
        canonical_data=envelope.state.canonical_data,
    )


def _atomic_write(path: Path, data: bytes) -> None:
    """原子写入已存在的 staging 父目录，并将写入错误归一为工件错误。"""

    temporary = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    try:
        with open(temporary, "xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError:
        raise JiejianError(ErrorCode.ARTIFACT_WRITE, "Runner V2 工件写入失败") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _cleanup(executor: HttpExecutor, snapshot: Any, case_id: str) -> None:
    response = executor.request("POST", snapshot.flow.reset_path, case_id=case_id, cleanup_request=True, test_mode=True)
    if not 200 <= response.status_code < 300:
        raise JiejianError(_V2_CLEANUP_FAILED, "Runner V2 cleanup failed")


def _request_payload(step: Any, case: Any, injection: Any) -> tuple[str, dict[str, Any]]:
    if injection.value == "PATH_RESOURCE_ID":
        return step.path.replace("{resource_id}", case.resource_ids[0]), dict(step.json_body)
    body = dict(step.json_body)
    body["resource_ids"] = list(case.resource_ids)
    return step.path, body


class RunnerV2Executor:
    def __init__(self, document: RunnerInputV2, *, environ: Mapping[str, str], staging: Path, clock: Callable[[], int], cancellation_requested: Callable[[], bool] | None = None) -> None:
        self.document = document
        self.snapshot = document.project_snapshot
        self.environ = environ
        self.staging = staging
        self.clock = clock
        self.cancellation_requested = cancellation_requested or (lambda: False)
        self.observer_specs = {item.observer_id: item for item in self.snapshot.observers}
        self.bindings = {item.requirement_id: item for item in self.snapshot.observer_bindings}
        self.subject_identities = {
            item.subject_id: self._identity_by_id(item.identity_id)
            for item in self.snapshot.subject_bindings
        }
        self.actions = {item.action_id: item for item in self.snapshot.contract.actions}
        self.steps = {item.id: item for item in self.snapshot.flow.steps}
        self.guard = TargetGuard(self.snapshot.target)
        self.guard.authorize_url(self.snapshot.target.base_url)
        used_identity_ids = {item.identity_id for item in self.snapshot.subject_bindings}
        identity_secrets = tuple(
            _secret_value(self.environ, identity.secret_ref, required=True) or ""
            for identity in self.snapshot.identities
            if identity.id in used_identity_ids
        )
        self.http = HttpExecutor(
            self.guard,
            cleanup_reserve=2 * len(self.snapshot.plan.cases),
            known_secrets=identity_secrets,
            cancellation_requested=self.cancellation_requested,
        )

    def _identity_by_id(self, identity_id: str) -> Any:
        for identity in self.snapshot.identities:
            if identity.id == identity_id:
                return identity
        raise JiejianError("V2_BINDING_INVALID", "Runner V2 identity binding is invalid")

    def _observer(self, binding: Any, spec: ObserverSpecV2, correlation: CorrelationV2, phase: ObservationPhase, cursors: tuple[AuditLogStartCursorV2, ...]) -> tuple[ObservationEnvelopeV2 | None, ObserverOutcomeV2, tuple[AuditLogStartCursorV2, ...]]:
        if spec.observer_type is ObserverType.OWNER_API:
            token = _secret_value(self.environ, binding.owner_api_credential_ref or "", required=True)
            adapter = OwnerApiObserverV2Adapter(spec=spec, utc_now_us=self.clock)
            try:
                envelope = adapter.observe(
                    self.http,
                    resource_id=correlation.resource_id,
                    owner_token=token or "",
                    case_id=correlation.case_id,
                    phase=phase,
                    known_secrets=(token or "",),
                )
                return envelope, evaluate_observer_outcome(envelope, required=spec.required), cursors
            except JiejianError as exc:
                if exc.code in {
                    ErrorCode.SCOPE_URL.value,
                    ErrorCode.SCOPE_HOST.value,
                    ErrorCode.SCOPE_PORT.value,
                    ErrorCode.SCOPE_PRIVATE_NETWORK.value,
                    ErrorCode.SCOPE_REDIRECT.value,
                    ErrorCode.EXEC_BUDGET.value,
                    ErrorCode.EXEC_RESPONSE_TOO_LARGE.value,
                    ErrorCode.EXEC_CANCELLED.value,
                    ErrorCode.SECRET_MISSING.value,
                }:
                    raise
                return None, _failure_outcome(spec), cursors
        kwargs = {
            "attempt_dir": self.staging.parent,
            "parent_environ": self.environ,
            "python_executable": sys.executable,
        }
        if spec.observer_type is ObserverType.READ_ONLY_SQLITE:
            result = run_sqlite_observer(spec, correlation, phase, **kwargs)
        elif spec.observer_type is ObserverType.STRUCTURED_AUDIT_LOG:
            result = run_audit_log_observer(spec, correlation, phase, start_cursors=cursors, **kwargs)
        elif spec.observer_type is ObserverType.ASYNC_TASK_STATUS:
            result = run_async_task_observer(spec, correlation, phase, **kwargs)
        elif spec.observer_type is ObserverType.AZURE_QUEUE_PEEK:
            result = run_azure_queue_observer(spec, correlation, phase, **kwargs)
        elif spec.observer_type is ObserverType.AZURE_BLOB_OBJECT:
            result = run_azure_blob_observer(spec, correlation, phase, **kwargs)
        else:
            return None, _failure_outcome(spec, "V2_OBSERVER_UNSUPPORTED"), cursors
        next_cursors = cursors
        if spec.observer_type is ObserverType.STRUCTURED_AUDIT_LOG and result.envelope and result.envelope.state:
            raw = result.envelope.state.canonical_data.get("next_offsets", ())
            try:
                next_cursors = tuple(AuditLogStartCursorV2.model_validate(item) for item in raw)
            except (TypeError, ValueError, ValidationError):
                return result.envelope, _failure_outcome(spec, "V2_OBSERVER_CURSOR_INVALID"), cursors
        return result.envelope, result.outcome, next_cursors

    def _observe_phase(
        self,
        case: Any,
        phase: ObservationPhase,
        envelopes: list[ObservationEnvelopeV2],
        outcomes: dict[str, ObserverOutcomeV2],
        facts: list[ObservationDecisionFact],
        cursors: dict[tuple[str, str], tuple[AuditLogStartCursorV2, ...]],
    ) -> bool:
        unavailable = False
        for resource_id in case.resource_ids:
            for requirement in case.required_observers:
                if requirement == "http":
                    continue
                binding = self.bindings[requirement]
                if phase not in binding.phases:
                    continue
                spec = self.observer_specs[binding.observer_id]
                correlation = CorrelationV2(case_id=case.case_id, resource_id=resource_id, request_marker=case.case_id)
                envelope, outcome, next_cursor = self._observer(
                    binding,
                    spec,
                    correlation,
                    phase,
                    cursors.get((requirement, resource_id), ()),
                )
                outcomes[spec.observer_id] = _aggregate_outcome(outcomes.get(spec.observer_id), outcome)
                cursors[(requirement, resource_id)] = next_cursor
                if envelope:
                    envelopes.append(envelope)
                    facts.append(_observer_fact(requirement, envelope))
                if outcome.status is not ObserverOutcomeStatus.AVAILABLE:
                    unavailable = True
                if self.cancellation_requested():
                    raise JiejianError(ErrorCode.EXEC_CANCELLED, "Runner V2 execution cancelled")
        return unavailable

    def run_case(self, case: Any) -> EvidenceV2:
        action_binding = next(item for item in self.snapshot.action_bindings if item.action_id == case.action_id)
        step = self.steps[action_binding.flow_step_id]
        action = self.actions[case.action_id]
        subject_identity = self.subject_identities[case.subject_id]
        subject_token = _secret_value(self.environ, subject_identity.secret_ref, required=True)
        envelopes: list[ObservationEnvelopeV2] = []
        outcomes: dict[str, ObserverOutcomeV2] = {}
        facts: list[ObservationDecisionFact] = []
        cursors: dict[tuple[str, str], tuple[AuditLogStartCursorV2, ...]] = {}
        request_path, request_body = _request_payload(step, case, action_binding.resource_injection)
        request: RequestFactV2 | None = None
        try:
            if self.cancellation_requested():
                raise JiejianError(ErrorCode.EXEC_CANCELLED, "Runner V2 execution cancelled")
            _cleanup(self.http, self.snapshot, case.case_id)
            before_failed = self._observe_phase(case, ObservationPhase.BEFORE, envelopes, outcomes, facts, cursors)
            if before_failed:
                request = _failure_request(case.case_id, case.subject_id, step.method, request_path, request_body, _V2_INCONCLUSIVE)
            else:
                try:
                    response = self.http.request(step.method, request_path, case_id=case.case_id, bearer_token=subject_token, json_body=request_body)
                    request = _request_fact(case.case_id, case.subject_id, step.method, request_path, request_body, response)
                except JiejianError as exc:
                    if exc.code == ErrorCode.EXEC_CANCELLED.value:
                        raise
                    if exc.code in {
                        ErrorCode.SCOPE_URL.value,
                        ErrorCode.SCOPE_HOST.value,
                        ErrorCode.SCOPE_PORT.value,
                        ErrorCode.SCOPE_PRIVATE_NETWORK.value,
                        ErrorCode.SCOPE_REDIRECT.value,
                        ErrorCode.EXEC_BUDGET.value,
                        ErrorCode.EXEC_RESPONSE_TOO_LARGE.value,
                    }:
                        raise
                    request = _failure_request(case.case_id, case.subject_id, step.method, request_path, request_body, exc.code if exc.code.isupper() else _V2_REQUEST_FAILED)
            if not before_failed:
                for phase in (ObservationPhase.AFTER, ObservationPhase.EVENTUAL):
                    self._observe_phase(case, phase, envelopes, outcomes, facts, cursors)
            if request is None:
                request = _failure_request(case.case_id, case.subject_id, step.method, request_path, request_body, _V2_REQUEST_FAILED)
            decision = CaseDecisionInput(
                case=case,
                action=action,
                expected_statuses=step.expected_statuses,
                request=RequestDecisionFact(status_code=request.status_code, failure_code=request.failure_code),
                required_observations=tuple(facts),
            )
            verdict, reason_codes = evaluate_permission_case_v2(decision)
            if any(item.status is not ObserverOutcomeStatus.AVAILABLE for item in outcomes.values()):
                verdict = CaseVerdict.INCONCLUSIVE
                reason_codes = tuple(sorted(set((*reason_codes, _V2_INCONCLUSIVE))))
            for requirement in case.required_observers:
                if requirement != "http":
                    binding = self.bindings[requirement]
                    if binding.observer_id not in outcomes:
                        outcomes[binding.observer_id] = _failure_outcome(self.observer_specs[binding.observer_id])
            return build_evidence_v2(
                schema_version="2",
                run_id=self.document.run_id,
                case_snapshot=case,
                finding_pre_identity=case.finding_pre_identity,
                request_fact=request,
                requirement_bindings=tuple(self.bindings[item] for item in case.required_observers),
                observations=tuple(envelopes),
                outcomes=tuple(outcomes.values()),
                verdict=verdict,
                reason_codes=tuple(reason_codes),
            )
        finally:
            _cleanup(self.http, self.snapshot, case.case_id)


def _result_error(
    document: RunnerInputV2,
    error: str,
    *,
    finished_at_us: int,
    cancelled: bool = False,
    safety_stopped: bool = False,
    cleanup_failed: bool = False,
) -> RunnerResultV2:
    """按一次尝试的固定完成时间构造失败、取消或安全停止结果。"""

    if cancelled:
        return RunnerResultV2(
            run_id=document.run_id, job_id=document.job_id, attempt=document.attempt, lease_owner=document.lease_owner,
            fencing_token=document.fencing_token, finished_at_us=finished_at_us, result_type=RunnerResultTypeV2.CANCELLED,
            run_lifecycle=RunLifecycle.CANCELLED, job_state=JobState.CANCELLED, verdict=None, reason_codes=(),
            cleanup=CleanupResultV2(status=CleanupStatusV2.SUCCEEDED), error=None,
            plan_fingerprint=document.project_snapshot.plan.plan_fingerprint, coverage_record_count=len(document.project_snapshot.plan.coverage),
            coverage_gap_count=len(document.project_snapshot.plan.gaps), evidence=(), artifacts=(),
        )
    if safety_stopped:
        return RunnerResultV2(
            run_id=document.run_id, job_id=document.job_id, attempt=document.attempt, lease_owner=document.lease_owner,
            fencing_token=document.fencing_token, finished_at_us=finished_at_us, result_type=RunnerResultTypeV2.SAFETY_STOPPED,
            run_lifecycle=RunLifecycle.SAFETY_STOPPED, job_state=JobState.SUCCEEDED, verdict=None,
            reason_codes=(error,), cleanup=CleanupResultV2(status=CleanupStatusV2.SUCCEEDED), error=None,
            plan_fingerprint=document.project_snapshot.plan.plan_fingerprint,
            coverage_record_count=len(document.project_snapshot.plan.coverage), coverage_gap_count=len(document.project_snapshot.plan.gaps),
            evidence=(), artifacts=(),
        )
    return RunnerResultV2(
        run_id=document.run_id, job_id=document.job_id, attempt=document.attempt, lease_owner=document.lease_owner,
        fencing_token=document.fencing_token, finished_at_us=finished_at_us, result_type=RunnerResultTypeV2.FATAL_ERROR,
        run_lifecycle=RunLifecycle.FAILED, job_state=JobState.FAILED, verdict=None, reason_codes=(error,),
        cleanup=CleanupResultV2(
            status=CleanupStatusV2.FAILED if cleanup_failed else CleanupStatusV2.NOT_REQUIRED,
            reason_codes=(error,) if cleanup_failed else (),
        ), error=RunnerErrorV2(code=error, retryable=False),
        plan_fingerprint=document.project_snapshot.plan.plan_fingerprint, coverage_record_count=len(document.project_snapshot.plan.coverage),
        coverage_gap_count=len(document.project_snapshot.plan.gaps), evidence=(), artifacts=(),
    )


def execute_runner_v2_attempt(input_path: Path, staging_dir: Path, *, environ: Mapping[str, str] | None = None, finished_at_us: Callable[[], int] | None = None) -> int:
    """加载 V2 输入并在隔离 staging 中串行生产 Evidence 与结果工件。"""

    environment = os.environ if environ is None else environ
    try:
        raw = input_path.read_bytes()
        preliminary = parse_runner_input_v2(raw)
        refs = required_secret_refs_v2(preliminary.project_snapshot)
        known_secrets = tuple(dict.fromkeys(environment[name.removeprefix("env:")] for name in refs if environment.get(name.removeprefix("env:"))))
        document = parse_runner_input_v2(raw, known_secrets=known_secrets)
    except (OSError, JiejianError, ValidationError, ValueError):
        return RUNNER_EXIT_PROTOCOL
    staging = staging_dir.resolve()
    finish_value = (finished_at_us or _now_us)()
    try:
        try:
            staging.mkdir(parents=True, exist_ok=False)
        except OSError:
            return RUNNER_EXIT_WRITE
        cancel_path = staging.parent / "cancel.requested"
        executor = RunnerV2Executor(
            document,
            environ=environment,
            staging=staging,
            clock=finished_at_us or _now_us,
            cancellation_requested=cancel_path.is_file,
        )
        evidence: list[EvidenceV2] = []
        try:
            for case in document.project_snapshot.plan.cases:
                evidence.append(executor.run_case(case))
        except JiejianError as exc:
            if exc.code == ErrorCode.EXEC_CANCELLED.value:
                _atomic_write(staging / "result.json", canonical_runner_v2_json_bytes(_result_error(document, exc.code, finished_at_us=finish_value, cancelled=True), known_secrets=known_secrets))
                return RUNNER_EXIT_OK
            safety_codes = {
                ErrorCode.SCOPE_URL.value,
                ErrorCode.SCOPE_HOST.value,
                ErrorCode.SCOPE_PORT.value,
                ErrorCode.SCOPE_PRIVATE_NETWORK.value,
                ErrorCode.SCOPE_REDIRECT.value,
                ErrorCode.EXEC_BUDGET.value,
                ErrorCode.EXEC_RESPONSE_TOO_LARGE.value,
            }
            cleanup_failed = exc.code == _V2_CLEANUP_FAILED
            result = _result_error(
                document,
                exc.code if exc.code.isupper() else "V2_RUNNER_FATAL",
                finished_at_us=finish_value,
                safety_stopped=exc.code in safety_codes,
                cleanup_failed=cleanup_failed,
            )
            _atomic_write(staging / "result.json", canonical_runner_v2_json_bytes(result, known_secrets=known_secrets))
            return RUNNER_EXIT_OK
        except Exception:
            result = _result_error(document, "V2_RUNNER_FATAL", finished_at_us=finish_value)
            _atomic_write(staging / "result.json", canonical_runner_v2_json_bytes(result, known_secrets=known_secrets))
            return RUNNER_EXIT_OK
        finally:
            executor.http.close()
        evidence_dir = staging / "artifacts" / "evidence"
        try:
            evidence_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise JiejianError(ErrorCode.ARTIFACT_WRITE, "Runner V2 证据目录创建失败") from None
        artifacts: list[StagedArtifactV2] = []
        for item in evidence:
            encoded = canonical_runner_v2_json_bytes(item, known_secrets=known_secrets)
            path = evidence_dir / f"{item.evidence_id}.json"
            _atomic_write(path, encoded)
            artifacts.append(StagedArtifactV2(path=path.relative_to(staging).as_posix(), byte_count=len(encoded), sha256=hashlib.sha256(encoded).hexdigest()))
        if not evidence and document.project_snapshot.plan.gaps:
            verdict = RunVerdict.INCONCLUSIVE
        elif any(item.verdict is CaseVerdict.VULNERABLE for item in evidence):
            verdict = RunVerdict.BLOCK
        elif any(item.verdict is CaseVerdict.INCONCLUSIVE for item in evidence) or document.project_snapshot.plan.gaps:
            verdict = RunVerdict.INCONCLUSIVE
        else:
            verdict = RunVerdict.PASS
        result = RunnerResultV2(
            run_id=document.run_id, job_id=document.job_id, attempt=document.attempt, lease_owner=document.lease_owner,
            fencing_token=document.fencing_token, finished_at_us=finish_value, result_type=RunnerResultTypeV2.SUCCESS,
            run_lifecycle=RunLifecycle.COMPLETED, job_state=JobState.SUCCEEDED, verdict=verdict, reason_codes=(),
            cleanup=CleanupResultV2(status=CleanupStatusV2.SUCCEEDED), error=None,
            plan_fingerprint=document.project_snapshot.plan.plan_fingerprint, coverage_record_count=len(document.project_snapshot.plan.coverage),
            coverage_gap_count=len(document.project_snapshot.plan.gaps), evidence=tuple(evidence), artifacts=tuple(artifacts),
        )
        _atomic_write(staging / "result.json", canonical_runner_v2_json_bytes(result, known_secrets=known_secrets))
        return RUNNER_EXIT_OK
    except JiejianError:
        return RUNNER_EXIT_WRITE
    except Exception:
        return RUNNER_EXIT_INTERNAL
