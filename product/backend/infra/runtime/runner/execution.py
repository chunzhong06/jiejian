# =============================================================================
# 复杂权限执行与 Evidence 暂存
#
# 定位
# 对冻结 RunnerInput 进行进程内受控执行，并形成尚未发布的事实工件。
#
# 职责
# 路由目标执行｜调度多面观察｜投影纯事实｜写入 staging RunnerResult 与 Evidence
#
# 边界
# HTTP 由 HttpExecutionAdapter 执行，权限结论由纯判定核心给出；本模块不负责 Worker publication。
#
# 调用链
# Worker → RunnerExecutor → ExecutionRouter/Observers/Verification → staging RunnerResult/Evidence
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

from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import AuditLogStartCursor, CausalityStatus, CleanupResult, CleanupStatus, Correlation, Evidence, ObservationCompleteness, ObservationEnvelope, ObservationPhase, ObserverOutcomeStatus, ObserverOutcome, ObserverSpec, ObserverType, ProvenanceType, RunnerError, RunnerInput, RunnerResultType, RunnerResult, StagedArtifact, ExecutionFact, ExecutionOutcome, ObservationFact, ObservedEffect, build_evidence, build_normalized_state, canonical_runner_json_bytes, canonical_runner_sha256, evaluate_observer_outcome, parse_runner_input, required_secret_refs
from product.backend.core.verification.permission_evaluation import CaseDecisionInput, evaluate_permission_case
from product.backend.infra.execution.http import HttpExecutionAdapter
from product.backend.infra.execution.router import ExecutionRouter
from product.backend.infra.observers.owner_api import OwnerApiObserverAdapter
from product.backend.infra.observers.async_task import run_async_task_observer
from product.backend.infra.observers.audit_log import run_audit_log_observer
from product.backend.infra.observers.azure_blob import run_azure_blob_observer
from product.backend.infra.observers.azure_queue import run_azure_queue_observer
from product.backend.infra.observers.sqlite import run_sqlite_observer


RUNNER_EXIT_OK = 0
RUNNER_EXIT_PROTOCOL = 64
RUNNER_EXIT_INTERNAL = 70
RUNNER_EXIT_WRITE = 74

_PHASE_ORDER = {
    ObservationPhase.BEFORE: 0,
    ObservationPhase.AFTER: 1,
    ObservationPhase.EVENTUAL: 2,
}
_PERMISSION_OBSERVER_INCOMPLETE = "REQUIRED_OBSERVER_INCOMPLETE"
_PERMISSION_REQUEST_FAILED = "REQUEST_FAILED"
_PERMISSION_CLEANUP_FAILED = "PERMISSION_CLEANUP_FAILED"


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


def _failure_outcome(spec: ObserverSpec, code: str = _PERMISSION_OBSERVER_INCOMPLETE) -> ObserverOutcome:
    return ObserverOutcome(
        observer_id=spec.observer_id,
        required=spec.required,
        status=ObserverOutcomeStatus.INCONCLUSIVE,
        reason_codes=(code,),
    )


def _aggregate_outcome(current: ObserverOutcome | None, incoming: ObserverOutcome) -> ObserverOutcome:
    if current is None:
        return incoming
    statuses = {current.status, incoming.status}
    status = ObserverOutcomeStatus.EXECUTION_ERROR if ObserverOutcomeStatus.EXECUTION_ERROR in statuses else ObserverOutcomeStatus.INCONCLUSIVE if ObserverOutcomeStatus.INCONCLUSIVE in statuses else ObserverOutcomeStatus.AVAILABLE
    return ObserverOutcome(
        observer_id=current.observer_id,
        required=current.required,
        status=status,
        reason_codes=tuple(sorted(set((*current.reason_codes, *incoming.reason_codes)))),
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
        raise JiejianError(ErrorCode.ARTIFACT_WRITE, "复杂权限执行工件写入失败") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class RunnerExecutor:
    """在单次 Runner attempt 内串行执行 case，并生产未发布 Evidence。"""

    def __init__(self, document: RunnerInput, *, environ: Mapping[str, str], staging: Path, clock: Callable[[], int], cancellation_requested: Callable[[], bool] | None = None) -> None:
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
        used_identity_ids = {item.identity_id for item in self.snapshot.subject_bindings}
        identity_secrets = tuple(
            _secret_value(self.environ, identity.secret_ref, required=True) or ""
            for identity in self.snapshot.identities
            if identity.id in used_identity_ids
        )
        self.http = HttpExecutionAdapter(
            self.snapshot.target,
            cleanup_reserve=2 * len(self.snapshot.plan.cases),
            known_secrets=identity_secrets,
            cancellation_requested=self.cancellation_requested,
            executor_process_id=os.getpid(),
        )
        self.router = ExecutionRouter((self.http,))

    def _identity_by_id(self, identity_id: str) -> Any:
        for identity in self.snapshot.identities:
            if identity.id == identity_id:
                return identity
        raise JiejianError("_BINDING_INVALID", "复杂权限执行身份绑定无效")

    def _observer(self, binding: Any, spec: ObserverSpec, correlation: Correlation, phase: ObservationPhase, cursors: tuple[AuditLogStartCursor, ...]) -> tuple[ObservationEnvelope | None, ObserverOutcome, tuple[AuditLogStartCursor, ...]]:
        """调用一个冻结 Observer，并把局部失败归一为可判定的观察结果。"""

        if spec.observer_type is ObserverType.OWNER_API:
            token = _secret_value(self.environ, binding.credential_ref or "", required=True)
            adapter = OwnerApiObserverAdapter(spec=spec, utc_now_us=self.clock)
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
            return None, _failure_outcome(spec, "_OBSERVER_UNSUPPORTED"), cursors
        next_cursors = cursors
        if spec.observer_type is ObserverType.STRUCTURED_AUDIT_LOG and result.envelope and result.envelope.state:
            raw = result.envelope.state.canonical_data.get("next_offsets", ())
            try:
                next_cursors = tuple(AuditLogStartCursor.model_validate(item) for item in raw)
            except (TypeError, ValueError, ValidationError):
                return result.envelope, _failure_outcome(spec, "_OBSERVER_CURSOR_INVALID"), cursors
        return result.envelope, result.outcome, next_cursors

    def _observe_phase(
        self,
        case: Any,
        phase: ObservationPhase,
        envelopes: list[ObservationEnvelope],
        outcomes: dict[str, ObserverOutcome],
        cursors: dict[tuple[str, str], tuple[AuditLogStartCursor, ...]],
    ) -> bool:
        """执行一个观察阶段；返回值只表示是否存在不可用的必需观察。"""

        unavailable = False
        for resource_id in case.resource_ids:
            for requirement in case.required_observations:
                binding = self.bindings[requirement]
                if phase not in binding.phases:
                    continue
                spec = self.observer_specs[binding.observer_id]
                correlation = Correlation(case_id=case.case_id, resource_id=resource_id, request_marker=case.case_id)
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
                # 安全不变量：必需观察不可用会保留为不完整事实，后续不得据此得出安全结论。
                if outcome.status is not ObserverOutcomeStatus.AVAILABLE:
                    unavailable = True
                if self.cancellation_requested():
                    raise JiejianError(ErrorCode.EXEC_CANCELLED, "复杂权限执行已取消")
        return unavailable

    def _observation_facts(
        self,
        case: Any,
        envelopes: list[ObservationEnvelope],
    ) -> tuple[ObservationFact, ...]:
        """把多阶段观察投影为纯事实，无法可靠解释时显式生成 UNKNOWN。"""

        facts: list[ObservationFact] = []
        for requirement in case.required_observations:
            binding = self.bindings[requirement]
            observer_id = binding.observer_id
            observer_type = binding.observer_type
            selected_all = [item for item in envelopes if item.observer_id == observer_id]
            for resource_id in case.resource_ids:
                selected = [item for item in selected_all if item.correlation.resource_id == resource_id]
                complete = bool(selected) and all(
                    item.completeness is ObservationCompleteness.COMPLETE
                    and item.causality is CausalityStatus.CORRELATED
                    and item.state is not None
                    for item in selected
                )
                if not complete:
                    facts.append(ObservationFact(requirement_id=requirement, resource_id=resource_id, effect=ObservedEffect.UNKNOWN, complete=False, reliable=False, reason_codes=(_PERMISSION_OBSERVER_INCOMPLETE,)))
                    continue
                states = [item.state for item in sorted(selected, key=lambda item: _PHASE_ORDER[item.phase])]
                effect = ObservedEffect.ABSENT
                if observer_type in {ObserverType.OWNER_API, ObserverType.READ_ONLY_SQLITE, ObserverType.AZURE_BLOB_OBJECT}:
                    if len(states) >= 2 and states[0].canonical_sha256 != states[-1].canonical_sha256:
                        effect = ObservedEffect.CONFIRMED
                elif observer_type is ObserverType.STRUCTURED_AUDIT_LOG:
                    records = [record for state in states for record in (state.canonical_data.get("records", ()) if isinstance(state.canonical_data, Mapping) else ())]
                    if any(isinstance(record, Mapping) and record.get("event_type") == "SIDE_EFFECT" and record.get("effect") == "APPLIED" for record in records):
                        effect = ObservedEffect.CONFIRMED
                elif observer_type is ObserverType.ASYNC_TASK_STATUS:
                    data = states[-1].canonical_data
                    if isinstance(data, Mapping) and data.get("task_state") == "SUCCESS" and isinstance(data.get("final_result"), Mapping) and data["final_result"].get("effect") == "APPLIED":
                        effect = ObservedEffect.CONFIRMED
                    elif not (isinstance(data, Mapping) and data.get("task_state") == "NOT_CREATED"):
                        facts.append(ObservationFact(requirement_id=requirement, resource_id=resource_id, effect=ObservedEffect.UNKNOWN, complete=False, reliable=False, reason_codes=("OBSERVATION_UNINTERPRETED",)))
                        continue
                elif observer_type is ObserverType.AZURE_QUEUE_PEEK:
                    data = states[-1].canonical_data
                    if not (isinstance(data, Mapping) and data.get("window_complete") is True and data.get("matched_count") == 0 and data.get("messages") == []):
                        if isinstance(data, Mapping) and data.get("matched_count", 0) > 0 and data.get("messages"):
                            effect = ObservedEffect.CONFIRMED
                        else:
                            facts.append(ObservationFact(requirement_id=requirement, resource_id=resource_id, effect=ObservedEffect.UNKNOWN, complete=False, reliable=False, reason_codes=("OBSERVATION_WINDOW_INCOMPLETE",)))
                            continue
                facts.append(ObservationFact(requirement_id=requirement, resource_id=resource_id, effect=effect, complete=True, reliable=True))
        return tuple(facts)

    def run_case(self, case: Any) -> Evidence:
        """执行单个冻结 case，并保证目标恢复后返回完整 Evidence。"""

        # --- 阶段：准备冻结绑定与请求 ---
        action_binding = next(item for item in self.snapshot.action_bindings if item.action_id == case.action_id)
        action = self.actions[case.action_id]
        subject_identity = self.subject_identities[case.subject_id]
        subject_token = _secret_value(self.environ, subject_identity.secret_ref, required=True)
        envelopes: list[ObservationEnvelope] = []
        outcomes: dict[str, ObserverOutcome] = {}
        cursors: dict[tuple[str, str], tuple[AuditLogStartCursor, ...]] = {}
        request_path = action_binding.relative_path_template
        request_body = dict(action_binding.json_body)
        if action_binding.resource_injection.value == "PATH_RESOURCE_ID":
            request_path = request_path.replace("{resource_id}", case.resource_ids[0])
        else:
            request_body["resource_ids"] = list(case.resource_ids)
        execution_binding = action_binding.model_copy(update={"relative_path_template": request_path, "json_body": request_body})
        execution: ExecutionFact
        try:
            # --- 阶段：恢复目标、执行前观察与受控请求 ---
            if self.cancellation_requested():
                raise JiejianError(ErrorCode.EXEC_CANCELLED, "复杂权限执行已取消")
            # 安全边界：每个 case 前后都执行恢复，避免跨 case 状态污染；finally 保证失败路径同样清理。
            self.router.cleanup(self.snapshot.target_type, self.snapshot.target.reset_path, case_id=case.case_id)
            before_failed = self._observe_phase(case, ObservationPhase.BEFORE, envelopes, outcomes, cursors)
            if before_failed:
                execution = ExecutionFact(case_id=case.case_id, action_id=case.action_id, target_type=self.snapshot.target_type, outcome=ExecutionOutcome.UNKNOWN, execution_marker=case.case_id, input_hash=_sha256(request_body), output_hash=hashlib.sha256(b"").hexdigest(), reason_codes=(_PERMISSION_OBSERVER_INCOMPLETE,))
            else:
                execution = self.router.execute(self.snapshot.target_type, execution_binding, case_id=case.case_id, action_id=case.action_id, bearer_token=subject_token)
            if not before_failed:
                for phase in (ObservationPhase.AFTER, ObservationPhase.EVENTUAL):
                    self._observe_phase(case, phase, envelopes, outcomes, cursors)
            # --- 阶段：投影事实并确定性判定 ---
            facts = list(self._observation_facts(case, envelopes))
            decision = CaseDecisionInput(
                case=case,
                action=action,
                execution=execution,
                observations=tuple(facts),
            )
            verdict, reason_codes = evaluate_permission_case(decision)
            if any(item.status is not ObserverOutcomeStatus.AVAILABLE for item in outcomes.values()):
                verdict = CaseVerdict.INCONCLUSIVE
                reason_codes = tuple(sorted(set((*reason_codes, _PERMISSION_OBSERVER_INCOMPLETE))))
            for requirement in case.required_observations:
                binding = self.bindings[requirement]
                if binding.observer_id not in outcomes:
                    outcomes[binding.observer_id] = _failure_outcome(self.observer_specs[binding.observer_id])
            return build_evidence(
                schema_version="2",
                run_id=self.document.run_id,
                case_snapshot=case,
                finding_pre_identity=case.finding_pre_identity,
                execution_fact=execution,
                requirement_bindings=tuple(self.bindings[item] for item in case.required_observations),
                observation_facts=tuple(facts),
                observations=tuple(envelopes),
                outcomes=tuple(outcomes.values()),
                verdict=verdict,
                reason_codes=tuple(reason_codes),
            )
        finally:
            # 失败语义：任何异常都不能跳过 case 后恢复，cleanup 失败由上层 attempt 归一处理。
            self.router.cleanup(self.snapshot.target_type, self.snapshot.target.reset_path, case_id=case.case_id)


def _result_error(
    document: RunnerInput,
    error: str,
    *,
    finished_at_us: int,
    cancelled: bool = False,
    safety_stopped: bool = False,
    cleanup_failed: bool = False,
) -> RunnerResult:
    """按一次尝试的固定完成时间构造失败、取消或安全停止结果。"""

    if cancelled:
        return RunnerResult(
            run_id=document.run_id, job_id=document.job_id, attempt=document.attempt, lease_owner=document.lease_owner,
            fencing_token=document.fencing_token, finished_at_us=finished_at_us, result_type=RunnerResultType.CANCELLED,
            run_lifecycle=RunLifecycle.CANCELLED, job_state=JobState.CANCELLED, verdict=None, reason_codes=(),
            cleanup=CleanupResult(status=CleanupStatus.SUCCEEDED), error=None,
            plan_fingerprint=document.project_snapshot.plan.plan_fingerprint, coverage_record_count=len(document.project_snapshot.plan.coverage),
            coverage_gap_count=len(document.project_snapshot.plan.gaps), evidence=(), artifacts=(),
        )
    if safety_stopped:
        return RunnerResult(
            run_id=document.run_id, job_id=document.job_id, attempt=document.attempt, lease_owner=document.lease_owner,
            fencing_token=document.fencing_token, finished_at_us=finished_at_us, result_type=RunnerResultType.SAFETY_STOPPED,
            run_lifecycle=RunLifecycle.SAFETY_STOPPED, job_state=JobState.SUCCEEDED, verdict=None,
            reason_codes=(error,), cleanup=CleanupResult(status=CleanupStatus.SUCCEEDED), error=None,
            plan_fingerprint=document.project_snapshot.plan.plan_fingerprint,
            coverage_record_count=len(document.project_snapshot.plan.coverage), coverage_gap_count=len(document.project_snapshot.plan.gaps),
            evidence=(), artifacts=(),
        )
    return RunnerResult(
        run_id=document.run_id, job_id=document.job_id, attempt=document.attempt, lease_owner=document.lease_owner,
        fencing_token=document.fencing_token, finished_at_us=finished_at_us, result_type=RunnerResultType.FATAL_ERROR,
        run_lifecycle=RunLifecycle.FAILED, job_state=JobState.FAILED, verdict=None, reason_codes=(error,),
        cleanup=CleanupResult(
            status=CleanupStatus.FAILED if cleanup_failed else CleanupStatus.NOT_REQUIRED,
            reason_codes=(error,) if cleanup_failed else (),
        ), error=RunnerError(code=error, retryable=False),
        plan_fingerprint=document.project_snapshot.plan.plan_fingerprint, coverage_record_count=len(document.project_snapshot.plan.coverage),
        coverage_gap_count=len(document.project_snapshot.plan.gaps), evidence=(), artifacts=(),
    )


def execute_attempt(input_path: Path, staging_dir: Path, *, environ: Mapping[str, str] | None = None, finished_at_us: Callable[[], int] | None = None) -> int:
    """加载复杂权限输入，并在隔离 staging 中串行生产 Evidence 与结果工件。"""

    environment = os.environ if environ is None else environ
    try:
        raw = input_path.read_bytes()
        preliminary = parse_runner_input(raw)
        refs = required_secret_refs(preliminary.project_snapshot)
        known_secrets = tuple(dict.fromkeys(environment[name.removeprefix("env:")] for name in refs if environment.get(name.removeprefix("env:"))))
        document = parse_runner_input(raw, known_secrets=known_secrets)
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
        executor = RunnerExecutor(
            document,
            environ=environment,
            staging=staging,
            clock=finished_at_us or _now_us,
            cancellation_requested=cancel_path.is_file,
        )
        evidence: list[Evidence] = []
        try:
            for case in document.project_snapshot.plan.cases:
                evidence.append(executor.run_case(case))
        except JiejianError as exc:
            if exc.code == ErrorCode.EXEC_CANCELLED.value:
                _atomic_write(staging / "result.json", canonical_runner_json_bytes(_result_error(document, exc.code, finished_at_us=finish_value, cancelled=True), known_secrets=known_secrets))
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
            cleanup_failed = exc.code == _PERMISSION_CLEANUP_FAILED
            result = _result_error(
                document,
                exc.code if exc.code.isupper() else "_RUNNER_FATAL",
                finished_at_us=finish_value,
                safety_stopped=exc.code in safety_codes,
                cleanup_failed=cleanup_failed,
            )
            _atomic_write(staging / "result.json", canonical_runner_json_bytes(result, known_secrets=known_secrets))
            return RUNNER_EXIT_OK
        except Exception:
            result = _result_error(document, "_RUNNER_FATAL", finished_at_us=finish_value)
            _atomic_write(staging / "result.json", canonical_runner_json_bytes(result, known_secrets=known_secrets))
            return RUNNER_EXIT_OK
        finally:
            executor.http.close()
        evidence_dir = staging / "artifacts" / "evidence"
        try:
            evidence_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise JiejianError(ErrorCode.ARTIFACT_WRITE, "复杂权限执行证据目录创建失败") from None
        artifacts: list[StagedArtifact] = []
        for item in evidence:
            encoded = canonical_runner_json_bytes(item, known_secrets=known_secrets)
            path = evidence_dir / f"{item.evidence_id}.json"
            _atomic_write(path, encoded)
            artifacts.append(StagedArtifact(path=path.relative_to(staging).as_posix(), byte_count=len(encoded), sha256=hashlib.sha256(encoded).hexdigest()))
        if not evidence and document.project_snapshot.plan.gaps:
            verdict = RunVerdict.INCONCLUSIVE
        elif any(item.verdict is CaseVerdict.VULNERABLE for item in evidence):
            verdict = RunVerdict.BLOCK
        elif any(item.verdict is CaseVerdict.INCONCLUSIVE for item in evidence) or document.project_snapshot.plan.gaps:
            verdict = RunVerdict.INCONCLUSIVE
        else:
            verdict = RunVerdict.PASS
        result = RunnerResult(
            run_id=document.run_id, job_id=document.job_id, attempt=document.attempt, lease_owner=document.lease_owner,
            fencing_token=document.fencing_token, finished_at_us=finish_value, result_type=RunnerResultType.SUCCESS,
            run_lifecycle=RunLifecycle.COMPLETED, job_state=JobState.SUCCEEDED, verdict=verdict, reason_codes=(),
            cleanup=CleanupResult(status=CleanupStatus.SUCCEEDED), error=None,
            plan_fingerprint=document.project_snapshot.plan.plan_fingerprint, coverage_record_count=len(document.project_snapshot.plan.coverage),
            coverage_gap_count=len(document.project_snapshot.plan.gaps), evidence=tuple(evidence), artifacts=tuple(artifacts),
        )
        _atomic_write(staging / "result.json", canonical_runner_json_bytes(result, known_secrets=known_secrets))
        return RUNNER_EXIT_OK
    except JiejianError:
        return RUNNER_EXIT_WRITE
    except Exception:
        return RUNNER_EXIT_INTERNAL
