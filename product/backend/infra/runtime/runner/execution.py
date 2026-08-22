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
import hmac
import json
import os
import secrets
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import AuditLogStartCursor, BearerIdentityBinding, CausalityStatus, CleanupResult, CleanupStatus, Correlation, DisclosureProof, Evidence, ObservationCompleteness, ObservationEnvelope, ObservationPhase, ObserverOutcomeStatus, ObserverOutcome, ObserverSpec, ObserverType, ProvenanceType, RunnerError, RunnerInput, RunnerResultType, RunnerResult, StagedArtifact, ExecutionFact, ExecutionOutcome, ObservationFact, ObservedEffect, TemporalClosure, TwinExecutionRole, aggregate_security_effect, build_evidence, build_normalized_state, canonical_runner_json_bytes, canonical_runner_sha256, evaluate_observer_outcome, parse_runner_input, required_secret_refs
from product.backend.core.verification.permission_evaluation import CaseDecisionInput, evaluate_permission_case
from product.backend.core.verification.permissions import PermissionExpectation
from product.backend.infra.execution.http import HttpExecutionAdapter, HttpResponse
from product.backend.infra.execution.http import extract_response_value
from product.backend.infra.execution.http_identity import HttpIdentityRuntime
from product.protocols.http import BaselineIntegrity, CASE_SUBJECT_IDENTITY, HttpOutcome, ValueSlotSource, build_baseline_fingerprint
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
    ObservationPhase.BASELINE: 0,
    ObservationPhase.BEFORE: 1,
    ObservationPhase.AFTER: 2,
    ObservationPhase.EVENTUAL: 3,
}
_PERMISSION_OBSERVER_INCOMPLETE = "REQUIRED_OBSERVER_INCOMPLETE"
_PERMISSION_REQUEST_FAILED = "REQUEST_FAILED"
_PERMISSION_CLEANUP_FAILED = "PERMISSION_CLEANUP_FAILED"


def _now_us() -> int:
    return time.time_ns() // 1_000


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _project_fields(value: Any, fields: tuple[str, ...], *, require_present: bool) -> tuple[dict[str, Any], bool]:
    """只投影 manifest 允许的字段；缺失字段不得被当作“不披露”。"""

    projected: dict[str, Any] = {}
    complete = isinstance(value, Mapping)
    for path in fields:
        current = value
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                if require_present:
                    complete = False
                current = None
                break
            current = current[part]
        projected[path] = current
    return projected, complete


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


def _apply_terminal_completion(
    execution: ExecutionFact,
    response: HttpResponse,
    classifier: Any,
    *,
    completion_bindings: Mapping[str, Any],
    envelopes: tuple[ObservationEnvelope, ...],
    case_id: str,
) -> ExecutionFact:
    """只用已绑定的异步 SUCCESS 终态解释 202，不重新发送目标请求。"""

    completion_id = classifier.completion_binding
    if response.status_code != 202 or completion_id is None:
        return execution
    binding = completion_bindings.get(completion_id)
    completed = any(
        envelope.observer_id == getattr(binding, "observer_id", None)
        and envelope.observer_type is ObserverType.ASYNC_TASK_STATUS
        and envelope.phase is ObservationPhase.EVENTUAL
        and envelope.correlation.case_id == case_id
        and envelope.completeness is ObservationCompleteness.COMPLETE
        and envelope.causality is CausalityStatus.CORRELATED
        and envelope.state is not None
        and envelope.state.canonical_data.get("task_state") == "SUCCESS"
        for envelope in envelopes
    )
    resolved = classifier.classify(response, terminal_completed=completed)
    outcome = {
        HttpOutcome.ACCEPTED: ExecutionOutcome.ACCEPTED,
        HttpOutcome.DENIED: ExecutionOutcome.DENIED,
        HttpOutcome.UNKNOWN: ExecutionOutcome.UNKNOWN,
    }[resolved]
    return execution.model_copy(
        update={
            "outcome": outcome,
            "reason_codes": () if outcome is not ExecutionOutcome.UNKNOWN else ("UNINTERPRETED_RESPONSE",),
        }
    )


def _bind_twin_baseline(
    baselines: dict[str, tuple[str, ...]],
    twin: Any,
    twin_role: TwinExecutionRole | None,
    integrities: tuple[BaselineIntegrity, ...],
) -> bool:
    """冻结 ALLOW 实际基线，并要求 DENY 在相同归一化基线上执行。"""

    if twin is None or twin_role is None:
        return True
    observed = tuple(
        item.observed_fingerprint
        for item in integrities
        if item.observed_fingerprint is not None
    )
    if len(observed) != len(integrities):
        return False
    if twin_role is TwinExecutionRole.ALLOW_CONTROL:
        baselines[twin.twin_id] = observed
        return True
    return baselines.get(twin.twin_id) == observed


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
        self.effects = {item.effect_id: item for item in self.snapshot.contract.effects}
        self.effect_bindings = {item.effect_id: item for item in self.snapshot.effect_bindings}
        self.disclosure_key = secrets.token_bytes(32)
        used_identity_ids = {item.identity_id for item in self.snapshot.subject_bindings}
        identity_secrets = tuple(
            value
            for reference in required_secret_refs(self.snapshot)
            if (value := _secret_value(self.environ, reference, required=True))
        )
        self.http = HttpExecutionAdapter(
            self.snapshot.target,
            cleanup_reserve=2 * len(self.snapshot.plan.cases),
            known_secrets=identity_secrets,
            cancellation_requested=self.cancellation_requested,
            executor_process_id=os.getpid(),
        )
        self.router = ExecutionRouter((self.http,))
        self.baseline_integrities: dict[str, tuple[BaselineIntegrity, ...]] = {}
        self.twin_baselines: dict[str, tuple[str, ...]] = {}

    def _identity_by_id(self, identity_id: str) -> Any:
        for identity in self.snapshot.identities:
            if identity.identity_id == identity_id:
                return identity
        raise JiejianError("_BINDING_INVALID", "复杂权限执行身份绑定无效")

    def _observer(self, binding: Any, spec: ObserverSpec, correlation: Correlation, phase: ObservationPhase, cursors: tuple[AuditLogStartCursor, ...]) -> tuple[ObservationEnvelope | None, ObserverOutcome, tuple[AuditLogStartCursor, ...]]:
        """调用一个冻结 Observer，并把局部失败归一为可判定的观察结果。"""

        if spec.observer_type is ObserverType.OWNER_API:
            token = _secret_value(self.environ, binding.credential_ref or "", required=True)
            adapter = OwnerApiObserverAdapter(spec=spec, utc_now_us=self.clock)
            owner_runtime = HttpIdentityRuntime(
                BearerIdentityBinding(secret_ref=binding.credential_ref or ""),
                resolve_secret=lambda reference: _secret_value(self.environ, reference, required=True),
                business_origin=self.snapshot.target.scope.base_url,
            )
            try:
                envelope = adapter.observe(
                    self.http,
                    resource_id=correlation.resource_id,
                    owner_token=token or "",
                    case_id=correlation.case_id,
                    phase=phase,
                    known_secrets=(token or "",),
                    identity_runtime=owner_runtime,
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
            finally:
                owner_runtime.close()
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
                    facts.append(ObservationFact(requirement_id=requirement, resource_id=resource_id, effect=ObservedEffect.UNKNOWN, complete=False, reliable=False, correlated=False, temporal_closure=TemporalClosure.UNKNOWN, reason_codes=(_PERMISSION_OBSERVER_INCOMPLETE,)))
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
                        facts.append(ObservationFact(requirement_id=requirement, resource_id=resource_id, effect=ObservedEffect.UNKNOWN, complete=False, reliable=False, correlated=True, temporal_closure=TemporalClosure.UNKNOWN, reason_codes=("OBSERVATION_UNINTERPRETED",)))
                        continue
                elif observer_type is ObserverType.AZURE_QUEUE_PEEK:
                    data = states[-1].canonical_data
                    if not (isinstance(data, Mapping) and data.get("window_complete") is True and data.get("matched_count") == 0 and data.get("messages") == []):
                        if isinstance(data, Mapping) and data.get("matched_count", 0) > 0 and data.get("messages"):
                            effect = ObservedEffect.CONFIRMED
                        else:
                            facts.append(ObservationFact(requirement_id=requirement, resource_id=resource_id, effect=ObservedEffect.UNKNOWN, complete=False, reliable=False, correlated=True, temporal_closure=TemporalClosure.OPEN, reason_codes=("OBSERVATION_WINDOW_INCOMPLETE",)))
                            continue
                phases = {item.phase for item in selected}
                closed = ObservationPhase.AFTER in phases and (
                    ObservationPhase.EVENTUAL not in binding.phases or ObservationPhase.EVENTUAL in phases
                )
                facts.append(ObservationFact(
                    requirement_id=requirement,
                    resource_id=resource_id,
                    effect=effect,
                    complete=True,
                    reliable=True,
                    correlated=True,
                    temporal_closure=TemporalClosure.CLOSED if closed else TemporalClosure.OPEN,
                    reason_codes=() if closed else ("TEMPORAL_WINDOW_OPEN",),
                ))
        return tuple(facts)

    def _disclosure_proof(
        self,
        effect: Any,
        binding: Any,
        *,
        resource_id: str,
        response: Any,
        envelopes: list[ObservationEnvelope],
        case_id: str,
    ) -> DisclosureProof | None:
        if effect.kind.value != "DATA_DISCLOSURE":
            return None
        baseline = next(
            (
                item for item in envelopes
                if item.phase is ObservationPhase.BASELINE
                and item.correlation.resource_id == resource_id
                and item.state is not None
                and item.observer_id in {
                    self.bindings[requirement].observer_id
                    for requirement in binding.required_channels
                }
            ),
            None,
        )
        owner_value = baseline.state.canonical_data if baseline is not None and baseline.state is not None else None
        response_value = response.data if response is not None else None
        owner_projection, owner_complete = _project_fields(owner_value, effect.protected_fields, require_present=True)
        response_projection, response_complete = _project_fields(response_value, effect.protected_fields, require_present=False)
        owner_digest = hmac.new(self.disclosure_key, _json_bytes(owner_projection), hashlib.sha256).hexdigest()
        response_digest = hmac.new(self.disclosure_key, _json_bytes(response_projection), hashlib.sha256).hexdigest()
        complete = owner_complete and response_complete
        return DisclosureProof(
            projection_version=binding.projection_version,
            projection_complete=complete,
            owner_digest=owner_digest,
            response_digest=response_digest,
            matched=complete and hmac.compare_digest(owner_digest, response_digest),
            correlation_digest=hashlib.sha256(f"{case_id}:{resource_id}".encode("utf-8")).hexdigest(),
        )

    def _security_effect_facts(
        self,
        case: Any,
        action: Any,
        observations: tuple[ObservationFact, ...],
        *,
        baseline_integrity: bool,
        response: Any,
        envelopes: list[ObservationEnvelope],
    ) -> tuple[Any, ...]:
        facts: list[Any] = []
        for effect_id in action.effect_ids:
            effect = self.effects[effect_id]
            binding = self.effect_bindings[effect_id]
            for resource_id in case.resource_ids:
                proof = self._disclosure_proof(
                    effect,
                    binding,
                    resource_id=resource_id,
                    response=response,
                    envelopes=envelopes,
                    case_id=case.case_id,
                )
                facts.append(aggregate_security_effect(
                    effect,
                    resource_id=resource_id,
                    required_requirement_ids=binding.required_channels,
                    corroborating_requirement_ids=binding.corroborating_channels,
                    observations=observations,
                    baseline_integrity=baseline_integrity,
                    disclosure_proof=proof,
                ))
        return tuple(facts)

    def _baseline_inconclusive(
        self,
        case: Any,
        action: Any,
        *,
        twin: Any,
        twin_role: TwinExecutionRole | None,
        envelopes: list[ObservationEnvelope],
        outcomes: dict[str, ObserverOutcome],
        reason_code: str,
    ) -> Evidence:
        """基线不可比时在 TARGET 前停止，并发布可解释的 INCONCLUSIVE 证据。"""

        observations = self._observation_facts(case, envelopes)
        effect_facts = self._security_effect_facts(
            case,
            action,
            observations,
            baseline_integrity=False,
            response=None,
            envelopes=envelopes,
        )
        execution = ExecutionFact(
            case_id=case.case_id,
            action_id=case.action_id,
            target_type=self.snapshot.target_type,
            outcome=ExecutionOutcome.UNKNOWN,
            execution_marker=case.case_id,
            input_hash=hashlib.sha256(b"").hexdigest(),
            output_hash=hashlib.sha256(b"").hexdigest(),
            reason_codes=(reason_code,),
        )
        for requirement in case.required_observations:
            binding = self.bindings[requirement]
            # TARGET 前停止意味着完整观察窗口不可能闭合；即使 BASELINE 单点可用，
            # 也必须把整体 Observer outcome 收敛为 INCONCLUSIVE。
            outcomes[binding.observer_id] = _failure_outcome(
                self.observer_specs[binding.observer_id], reason_code
            )
        return build_evidence(
            schema_version="3",
            run_id=self.document.run_id,
            case_snapshot=case,
            twin_snapshot=twin,
            twin_role=twin_role,
            allow_control_valid=False,
            baseline_integrity=False,
            finding_pre_identity=case.finding_pre_identity,
            execution_fact=execution,
            requirement_bindings=tuple(self.bindings[item] for item in case.required_observations),
            observation_facts=observations,
            security_effect_facts=effect_facts,
            observations=tuple(envelopes),
            outcomes=tuple(outcomes.values()),
            verdict=CaseVerdict.INCONCLUSIVE,
            reason_codes=(reason_code,),
        )

    def run_case(self, case: Any, *, twin: Any = None, twin_role: TwinExecutionRole | None = None, allow_control_valid: bool = False) -> Evidence:
        """按冻结顺序执行一个工作流，并把动态值限制在当前 case 内存。"""

        workflow = next(item for item in self.snapshot.workflow_bindings if item.action_id == case.action_id)
        action = self.actions[case.action_id]
        envelopes: list[ObservationEnvelope] = []
        outcomes: dict[str, ObserverOutcome] = {}
        cursors: dict[tuple[str, str], tuple[AuditLogStartCursor, ...]] = {}
        outputs: dict[str, dict[str, Any]] = {}
        required_identity_ids = {
            self.subject_identities[case.subject_id].identity_id
            if step.identity_id == CASE_SUBJECT_IDENTITY
            else step.identity_id
            for step in workflow.steps
        }
        runtimes = {
            identity.identity_id: HttpIdentityRuntime(
                identity.binding,
                resolve_secret=lambda reference: _secret_value(self.environ, reference, required=True),
                business_origin=self.snapshot.target.scope.base_url,
            )
            for identity in self.snapshot.identities
            if identity.identity_id in required_identity_ids
        }
        identity_definitions = {identity.identity_id: identity for identity in self.snapshot.identities}
        execution: ExecutionFact | None = None
        target_started = False

        def runtime_for(step: Any) -> HttpIdentityRuntime:
            identity_id = self.subject_identities[case.subject_id].identity_id if step.identity_id == CASE_SUBJECT_IDENTITY else step.identity_id
            return runtimes[identity_id]

        def ordered_steps() -> tuple[Any, ...]:
            pending = {step.id: step for step in workflow.steps}
            ordered: list[Any] = []
            while pending:
                ready = [step for step in pending.values() if set(step.depends_on_step_ids).issubset({item.id for item in ordered})]
                if not ready:
                    raise JiejianError(ErrorCode.SETUP_STEP_FAILED, "工作流步骤依赖无法满足")
                for step in sorted(ready, key=lambda item: item.id):
                    ordered.append(step)
                    pending.pop(step.id)
            return tuple(ordered)

        def values_for(step: Any) -> dict[str, Any]:
            values: dict[str, Any] = {}
            for slot in step.input_slots:
                if slot.source.value == "CASE_SUBJECT_ID":
                    value: Any = case.subject_id
                elif slot.source.value == "CASE_RESOURCE_ID":
                    value = case.resource_ids[0]
                elif slot.source.value == "FIXED_LITERAL":
                    value = slot.literal
                elif slot.source.value == "SECRET_REF":
                    value = _secret_value(self.environ, slot.secret_ref or "", required=True)
                else:
                    if slot.producer_step_id not in outputs:
                        raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "动态值生产步骤尚未完成")
                    value = outputs[slot.producer_step_id].get(slot.slot_id)
                    if value is None:
                        raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "动态值提取为空")
                if isinstance(value, str) and len(value) > slot.max_length:
                    raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "动态值超过长度预算")
                values[slot.slot_id] = value
            return values

        try:
            if self.cancellation_requested():
                raise JiejianError(ErrorCode.EXEC_CANCELLED, "复杂权限执行已取消")
            reset_path = self.snapshot.target.reset_path
            if workflow.reset_strategy.kind.value == "RESET_ENDPOINT":
                reset_path = workflow.reset_strategy.path
            else:
                raise JiejianError(ErrorCode.BASELINE_INVALID, "当前工作流 reset strategy 无可执行恢复器")
            self.http.cleanup(reset_path, case_id=case.case_id)
            for identity_id, runtime in runtimes.items():
                try:
                    identity = identity_definitions[identity_id]
                    bootstrap_outputs: dict[str, dict[str, Any]] = {}

                    def send_bootstrap(request_or_path: Any, *, method: str = "POST", data: Any = None, auth: bool = False, auth_scope: Any = None, bootstrap: bool = False) -> Any:
                        if isinstance(request_or_path, str):
                            return self.http.request(
                                method,
                                request_or_path,
                                case_id=case.case_id,
                                data=data,
                                identity_runtime=runtime,
                                bootstrap_request=True,
                                auth_scope=auth_scope if auth else None,
                            )
                        template = request_or_path.request_template
                        slot_values: dict[str, Any] = {}
                        for slot in template.input_slots:
                            if slot.source is ValueSlotSource.FIXED_LITERAL:
                                value = slot.literal
                            elif slot.source is ValueSlotSource.SECRET_REF:
                                value = _secret_value(self.environ, slot.secret_ref or "", required=True)
                            else:
                                value = bootstrap_outputs.get(slot.producer_step_id or "", {}).get(slot.slot_id)
                            if value is None:
                                raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "身份 Bootstrap 动态值不可用")
                            slot_values[slot.slot_id] = value
                        response = self.http.request(
                            template.method,
                            template.path,
                            case_id=case.case_id,
                            query=template.query,
                            headers=template.headers,
                            body=template.body,
                            slot_values=slot_values,
                            identity_runtime=runtime,
                            bootstrap_request=True,
                        )
                        extracted = {
                            extractor.extractor_id: extract_response_value(response, extractor)
                            for extractor in template.response_extractors
                        }
                        bootstrap_outputs[request_or_path.template_id] = extracted
                        csrf_slot_id = getattr(identity.binding, "csrf_slot_id", None)
                        if csrf_slot_id is not None and csrf_slot_id in extracted:
                            extractor = next(item for item in template.response_extractors if item.extractor_id == csrf_slot_id)
                            runtime.set_csrf(
                                csrf_slot_id,
                                str(extracted[csrf_slot_id]),
                                origin=self.snapshot.target.scope.base_url,
                                max_length=extractor.max_length,
                            )
                        return response

                    runtime.bootstrap(send_bootstrap, requests=identity.bootstrap_requests)
                except JiejianError as exc:
                    raise JiejianError(ErrorCode.IDENTITY_PREPARATION_FAILED, "身份准备失败") from exc
            ordered = ordered_steps()
            for step in ordered:
                if step.purpose.value != "SETUP":
                    continue
                try:
                    fact, response = self.http.execute_detailed(step.request_template, case_id=case.case_id, action_id=case.action_id, classifier=step.classifier, slot_values=values_for(step), identity_runtime=runtime_for(step))
                    if fact.outcome is not ExecutionOutcome.ACCEPTED:
                        raise JiejianError(ErrorCode.SETUP_STEP_FAILED, "SETUP 步骤未被接受")
                    outputs[step.id] = {extractor.extractor_id: extract_response_value(response, extractor) for extractor in step.output_extractors}
                except JiejianError as exc:
                    if exc.code in {ErrorCode.VALUE_EXTRACTION_FAILED.value, ErrorCode.SECRET_MISSING.value}:
                        raise
                    raise JiejianError(ErrorCode.SETUP_STEP_FAILED, "SETUP 步骤失败") from exc
            baseline_failed = self._observe_phase(case, ObservationPhase.BASELINE, envelopes, outcomes, cursors)
            if workflow.baseline_projections and baseline_failed:
                self.baseline_integrities[case.case_id] = (
                    BaselineIntegrity(
                        mode=workflow.baseline_projections[0].integrity_mode,
                        expected_fingerprint=workflow.baseline_projections[0].expected_fingerprint,
                        observed_fingerprint=None,
                        valid=False,
                        reason_codes=("BASELINE_OBSERVATION_INCOMPLETE",),
                    ),
                )
                return self._baseline_inconclusive(
                    case,
                    action,
                    twin=twin,
                    twin_role=twin_role,
                    envelopes=envelopes,
                    outcomes=outcomes,
                    reason_code="BASELINE_OBSERVATION_INCOMPLETE",
                )
            integrities: list[BaselineIntegrity] = []
            baseline_envelopes = [item for item in envelopes if item.phase is ObservationPhase.BASELINE]
            relationship_payload = case.model_dump(
                mode="json",
                include={"subject_id", "relation_paths", "context"},
            )
            if twin is not None:
                for field_name in twin.mutation.changed_fields:
                    relationship_payload.pop(field_name, None)
            relationship_fingerprint = hashlib.sha256(
                _json_bytes(relationship_payload)
            ).hexdigest()
            for projection in workflow.baseline_projections:
                for resource_id in case.resource_ids:
                    envelope = next((item for item in baseline_envelopes if item.correlation.resource_id == resource_id and item.state is not None), None)
                    if envelope is None or envelope.state is None:
                        raise JiejianError(ErrorCode.BASELINE_INVALID, "BASELINE 缺少权威资源状态")
                    fingerprint = build_baseline_fingerprint(
                        logical_resource_handle=projection.logical_resource_handle,
                        normalized_resource_state=envelope.state.canonical_sha256,
                        workflow_state=workflow.workflow_fingerprint or "",
                        relationship_projection=relationship_fingerprint,
                        effect_projection=hashlib.sha256(_json_bytes(action.model_dump(mode="json"))).hexdigest(),
                        normalization_version=projection.normalization_version,
                        projection_version=projection.projection_version,
                    )
                    valid = projection.expected_fingerprint is None or projection.expected_fingerprint == fingerprint.fingerprint
                    integrities.append(BaselineIntegrity(
                        mode=projection.integrity_mode,
                        expected_fingerprint=projection.expected_fingerprint,
                        observed_fingerprint=fingerprint.fingerprint,
                        valid=valid,
                        reason_codes=() if valid else ("BASELINE_FINGERPRINT_MISMATCH",),
                    ))
            frozen_integrities = tuple(integrities)
            twin_baseline_valid = _bind_twin_baseline(
                self.twin_baselines,
                twin,
                twin_role,
                frozen_integrities,
            )
            if not twin_baseline_valid:
                frozen_integrities = tuple(
                    item.model_copy(
                        update={
                            "valid": False,
                            "reason_codes": tuple(
                                sorted(set((*item.reason_codes, "TWIN_BASELINE_MISMATCH")))
                            ),
                        }
                    )
                    for item in frozen_integrities
                )
            self.baseline_integrities[case.case_id] = frozen_integrities
            baseline_valid = (
                bool(workflow.baseline_projections)
                and twin_baseline_valid
                and all(item.valid for item in frozen_integrities)
            )
            if not baseline_valid:
                return self._baseline_inconclusive(
                    case,
                    action,
                    twin=twin,
                    twin_role=twin_role,
                    envelopes=envelopes,
                    outcomes=outcomes,
                    reason_code=(
                        "TWIN_BASELINE_MISMATCH"
                        if not twin_baseline_valid
                        else "BASELINE_INTEGRITY_INVALID"
                    ),
                )
            before_failed = self._observe_phase(case, ObservationPhase.BEFORE, envelopes, outcomes, cursors)
            if before_failed:
                raise JiejianError(ErrorCode.OBSERVER_INCOMPLETE, "BEFORE 观察不完整")
            target = next(step for step in ordered if step.id == workflow.target_step_id)
            target_started = True
            execution, response = self.http.execute_detailed(target.request_template, case_id=case.case_id, action_id=case.action_id, classifier=target.classifier, slot_values=values_for(target), identity_runtime=runtime_for(target))
            if execution.outcome is ExecutionOutcome.FAILED:
                raise JiejianError(ErrorCode.TARGET_EXECUTION_FAILED, "TARGET 请求失败")
            outputs[target.id] = {extractor.extractor_id: extract_response_value(response, extractor) for extractor in target.output_extractors}
            for phase in (ObservationPhase.AFTER, ObservationPhase.EVENTUAL):
                self._observe_phase(case, phase, envelopes, outcomes, cursors)
            execution = _apply_terminal_completion(
                execution,
                response,
                target.classifier,
                completion_bindings=self.bindings,
                envelopes=tuple(envelopes),
                case_id=case.case_id,
            )
            # --- 阶段：投影事实并确定性判定 ---
            facts = list(self._observation_facts(case, envelopes))
            effect_facts = self._security_effect_facts(
                case,
                action,
                tuple(facts),
                baseline_integrity=baseline_valid,
                response=response,
                envelopes=envelopes,
            )
            decision = CaseDecisionInput(
                case=case,
                action=action,
                execution=execution,
                effects=effect_facts,
                twin_role=twin_role,
                allow_control_valid=True if twin_role is TwinExecutionRole.ALLOW_CONTROL else allow_control_valid,
                baseline_integrity=baseline_valid,
            )
            verdict, reason_codes = evaluate_permission_case(decision)
            confirmed_effect = any(item.state is ObservedEffect.CONFIRMED for item in effect_facts)
            if any(item.status is not ObserverOutcomeStatus.AVAILABLE for item in outcomes.values()) and not (
                verdict is CaseVerdict.VULNERABLE and confirmed_effect
            ):
                verdict = CaseVerdict.INCONCLUSIVE
                reason_codes = tuple(sorted(set((*reason_codes, _PERMISSION_OBSERVER_INCOMPLETE))))
            for requirement in case.required_observations:
                binding = self.bindings[requirement]
                if binding.observer_id not in outcomes:
                    outcomes[binding.observer_id] = _failure_outcome(self.observer_specs[binding.observer_id])
            is_allow_control = twin_role is TwinExecutionRole.ALLOW_CONTROL or (
                twin_role is None
                and all(item is PermissionExpectation.ALLOW for item in case.expectations)
            )
            evidence = build_evidence(
                schema_version="3",
                run_id=self.document.run_id,
                case_snapshot=case,
                twin_snapshot=twin,
                twin_role=twin_role,
                allow_control_valid=(verdict is CaseVerdict.SAFE) if is_allow_control else allow_control_valid,
                baseline_integrity=baseline_valid,
                finding_pre_identity=case.finding_pre_identity,
                execution_fact=execution,
                requirement_bindings=tuple(self.bindings[item] for item in case.required_observations),
                observation_facts=tuple(facts),
                security_effect_facts=effect_facts,
                observations=tuple(envelopes),
                outcomes=tuple(outcomes.values()),
                verdict=verdict,
                reason_codes=tuple(reason_codes),
            )
            # 清理只能发生在安全事实聚合与确定性判定之后，避免改变本次证据窗口。
            for step in reversed(ordered):
                if step.purpose.value != "CLEANUP":
                    continue
                try:
                    self.http.execute_detailed(step.request_template, case_id=case.case_id, action_id=case.action_id, classifier=step.classifier, slot_values=values_for(step), identity_runtime=runtime_for(step))
                except JiejianError as exc:
                    raise JiejianError(ErrorCode.CLEANUP_FAILED, "CLEANUP 步骤失败") from exc
            return evidence
        finally:
            try:
                self.http.cleanup(self.snapshot.target.reset_path, case_id=case.case_id)
            except JiejianError:
                if target_started:
                    raise JiejianError(ErrorCode.CLEANUP_FAILED, "目标恢复失败") from None
            for runtime in runtimes.values():
                runtime.close()


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
            paired_case_ids: set[str] = set()
            for twin in document.project_snapshot.differential_plan.twins:
                allow_evidence = executor.run_case(
                    twin.allow_case,
                    twin=twin,
                    twin_role=TwinExecutionRole.ALLOW_CONTROL,
                    allow_control_valid=True,
                )
                evidence.append(allow_evidence)
                evidence.append(executor.run_case(
                    twin.deny_case,
                    twin=twin,
                    twin_role=TwinExecutionRole.DENY_VARIANT,
                    allow_control_valid=allow_evidence.verdict is CaseVerdict.SAFE,
                ))
                paired_case_ids.update((twin.allow_case.case_id, twin.deny_case.case_id))
            for case in document.project_snapshot.plan.cases:
                if case.case_id not in paired_case_ids:
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
