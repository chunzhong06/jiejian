# =============================================================================
# Web Target Runtime
#
# 定位
#   Target Runtime Port 的当前唯一生产实现，封装一次 Web attempt 与每 Case 状态。
#
# 职责
#   管理 Web 身份与工作流｜执行唯一 TARGET｜归约响应、基线与 Owner API 观察｜清理
#
# 边界
#   不计算 Verdict、Finding、Report 或 Gate，不把 HTTP Response 暴露给通用 Runner。
#
# 调用链
#   runner/composition → WebTargetRuntimeFactory → WebTargetRuntime / CaseSession
# =============================================================================

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from collections.abc import Mapping
from typing import Any

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.verification.facts import (
    DisclosureProof,
    ExecutionFact,
    ExecutionOutcome,
    TargetType,
)
from product.backend.core.verification.permissions.coverage import PermissionMutationCase
from product.backend.core.verification.permissions import (
    ActionDefinition,
    SecurityEffectDefinition,
)
from product.backend.infra.execution.port import (
    ExecutionSnapshotView,
    TargetBaselineResult,
    TargetCaseSession,
    TargetCleanupError,
    TargetCleanupIssue,
    TargetObservationResult,
    TargetRuntime,
    TargetRuntimeContext,
)
from product.backend.infra.execution.web.adapter import (
    HttpExecutionAdapter,
    HttpResponse,
    WebTargetGuard,
    extract_response_value,
)
from product.backend.infra.execution.web.identity import HttpIdentityRuntime
from product.backend.infra.observers.owner_api import OwnerApiObserverAdapter
from product.protocols import (
    BearerIdentityBinding,
    CausalityStatus,
    ObservationCompleteness,
    ObservationEnvelope,
    ObservationPhase,
    ObserverRequirementBinding,
    ObserverSpec,
    ObserverType,
    evaluate_observer_outcome,
    CleanupIssueCode,
)
from product.protocols.web.profile import (
    WebExecutionSnapshot,
    required_web_secret_refs,
)
from product.protocols.web.workflow import (
    CASE_SUBJECT_IDENTITY,
    HttpOutcome,
    ValueSlotSource,
    build_baseline_fingerprint,
)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _secret_value(
    environ: Mapping[str, str],
    reference: str,
    *,
    required: bool,
) -> str | None:
    value = environ.get(reference.removeprefix("env:"))
    if not value and required:
        raise JiejianError(ErrorCode.SECRET_MISSING, "执行所需秘密不可用")
    return value or None


def _project_fields(
    value: Any,
    fields: tuple[str, ...],
    *,
    require_present: bool,
) -> tuple[dict[str, Any], bool]:
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


def _apply_terminal_completion(
    execution: ExecutionFact,
    response: HttpResponse,
    classifier: Any,
    *,
    completion_bindings: Mapping[str, ObserverRequirementBinding],
    observations: tuple[ObservationEnvelope, ...],
    case_id: str,
) -> ExecutionFact:
    """只解释已保存的 202 响应与观察事实，不再次操作目标。"""

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
        for envelope in observations
    )
    outcome = ExecutionOutcome(
        classifier.classify(response, terminal_completed=completed).value
    )
    return execution.model_copy(
        update={
            "outcome": outcome,
            "reason_codes": (
                ()
                if outcome is not ExecutionOutcome.UNKNOWN
                else ("UNINTERPRETED_RESPONSE",)
            ),
        }
    )


class WebTargetRuntimeFactory:
    """严格创建 Web V1 Runtime；不根据结构猜测其他 Target。"""

    kind = "WEB"

    def create(
        self,
        snapshot: ExecutionSnapshotView,
        context: TargetRuntimeContext,
    ) -> TargetRuntime:
        if (
            not isinstance(snapshot, WebExecutionSnapshot)
            or snapshot.target_type is not TargetType.WEB
        ):
            raise JiejianError(ErrorCode.EXEC_REQUEST, "Web 执行快照类型无效")
        return WebTargetRuntime(snapshot, context)


class WebTargetRuntime:
    """一个 attempt 共享请求预算，但不共享 Case 身份或动态状态。"""

    def __init__(
        self,
        snapshot: WebExecutionSnapshot,
        context: TargetRuntimeContext,
    ) -> None:
        self.snapshot = snapshot
        self.context = context
        known_secrets = tuple(
            value
            for reference in required_web_secret_refs(snapshot)
            if (value := _secret_value(context.environ, reference, required=True))
        )
        reserved_origins = (
            (context.control_origin,) if context.control_origin is not None else ()
        )
        self.guard = WebTargetGuard(
            snapshot.target,
            reserved_origins=reserved_origins,
        )
        self.adapter = HttpExecutionAdapter(
            snapshot.target,
            cleanup_reserve=2 * len(snapshot.plan.cases),
            known_secrets=known_secrets,
            cancellation_requested=context.cancellation_requested,
            executor_process_id=os.getpid(),
            reserved_origins=reserved_origins,
        )
        self._subject_identities = {
            binding.subject_id: self._identity_by_id(binding.identity_id)
            for binding in snapshot.subject_bindings
        }
        self._effect_bindings = {
            binding.effect_id: binding for binding in snapshot.effect_bindings
        }
        self._disclosure_key = secrets.token_bytes(32)
        self._closed = False
        self.baseline_integrities: dict[str, tuple[Any, ...]] = {}

    def _identity_by_id(self, identity_id: str) -> Any:
        for identity in self.snapshot.identities:
            if identity.identity_id == identity_id:
                return identity
        raise JiejianError("_BINDING_INVALID", "复杂权限执行身份绑定无效")

    def open_case(
        self,
        case: PermissionMutationCase,
        action: ActionDefinition,
    ) -> TargetCaseSession:
        if self._closed:
            raise RuntimeError("target runtime is closed")
        return WebTargetCaseSession(self, case, action)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.adapter.close()


class WebTargetCaseSession:
    """隔离一个 Case 的身份、动态值、响应投影与清理状态。"""

    def __init__(
        self,
        runtime: WebTargetRuntime,
        case: PermissionMutationCase,
        action: ActionDefinition,
    ) -> None:
        self.runtime = runtime
        self.snapshot = runtime.snapshot
        self.context = runtime.context
        self.case = case
        self.action = action
        self.workflow = next(
            item
            for item in self.snapshot.workflow_bindings
            if item.action_id == case.action_id
        )
        self._bindings = {
            item.requirement_id: item for item in self.snapshot.observer_bindings
        }
        self._outputs: dict[str, dict[str, Any]] = {}
        self._identities: dict[str, HttpIdentityRuntime] = {}
        self._identity_definitions = {
            item.identity_id: item for item in self.snapshot.identities
        }
        self._ordered_steps = self._order_steps()
        self._execution: ExecutionFact | None = None
        self._response: HttpResponse | None = None
        self._prepared = False
        self._target_executed = False
        self._cleaned = False
        self._self_target_blocked = False

    def _order_steps(self) -> tuple[Any, ...]:
        pending = {step.id: step for step in self.workflow.steps}
        ordered: list[Any] = []
        while pending:
            ready = [
                step
                for step in pending.values()
                if set(step.depends_on_step_ids).issubset(
                    {item.id for item in ordered}
                )
            ]
            if not ready:
                raise JiejianError(
                    ErrorCode.SETUP_STEP_FAILED,
                    "工作流步骤依赖无法满足",
                )
            for step in sorted(ready, key=lambda item: item.id):
                ordered.append(step)
                pending.pop(step.id)
        return tuple(ordered)

    def _runtime_for(self, step: Any) -> HttpIdentityRuntime:
        if step.identity_id == CASE_SUBJECT_IDENTITY:
            identity_id = self.runtime._subject_identities[
                self.case.subject_id
            ].identity_id
        else:
            identity_id = step.identity_id
        return self._identities[identity_id]

    def _values_for(self, step: Any) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for slot in step.input_slots:
            if slot.source is ValueSlotSource.CASE_SUBJECT_ID:
                value: Any = self.case.subject_id
            elif slot.source is ValueSlotSource.CASE_RESOURCE_ID:
                value = self.case.resource_ids[0]
            elif slot.source is ValueSlotSource.FIXED_LITERAL:
                value = slot.literal
            elif slot.source is ValueSlotSource.SECRET_REF:
                value = _secret_value(
                    self.context.environ,
                    slot.secret_ref or "",
                    required=True,
                )
            else:
                if slot.producer_step_id not in self._outputs:
                    raise JiejianError(
                        ErrorCode.VALUE_EXTRACTION_FAILED,
                        "动态值生产步骤尚未完成",
                    )
                value = self._outputs[slot.producer_step_id].get(slot.slot_id)
                if value is None:
                    raise JiejianError(
                        ErrorCode.VALUE_EXTRACTION_FAILED,
                        "动态值提取为空",
                    )
            if isinstance(value, str) and len(value) > slot.max_length:
                raise JiejianError(
                    ErrorCode.VALUE_EXTRACTION_FAILED,
                    "动态值超过长度预算",
                )
            values[slot.slot_id] = value
        return values

    def _bootstrap_identity(
        self,
        identity_id: str,
        identity_runtime: HttpIdentityRuntime,
    ) -> None:
        identity = self._identity_definitions[identity_id]
        bootstrap_outputs: dict[str, dict[str, Any]] = {}

        def send_bootstrap(
            request_or_path: Any,
            *,
            method: str = "POST",
            data: Any = None,
            auth: bool = False,
            auth_scope: Any = None,
            bootstrap: bool = False,
        ) -> Any:
            del bootstrap
            if isinstance(request_or_path, str):
                return self.runtime.adapter.request(
                    method,
                    request_or_path,
                    case_id=self.case.case_id,
                    data=data,
                    identity_runtime=identity_runtime,
                    bootstrap_request=True,
                    auth_scope=auth_scope if auth else None,
                )
            template = request_or_path.request_template
            slot_values: dict[str, Any] = {}
            for slot in template.input_slots:
                if slot.source is ValueSlotSource.FIXED_LITERAL:
                    value = slot.literal
                elif slot.source is ValueSlotSource.SECRET_REF:
                    value = _secret_value(
                        self.context.environ,
                        slot.secret_ref or "",
                        required=True,
                    )
                else:
                    value = bootstrap_outputs.get(
                        slot.producer_step_id or "", {}
                    ).get(slot.slot_id)
                if value is None:
                    raise JiejianError(
                        ErrorCode.VALUE_EXTRACTION_FAILED,
                        "身份 Bootstrap 动态值不可用",
                    )
                slot_values[slot.slot_id] = value
            response = self.runtime.adapter.request(
                template.method,
                template.path,
                case_id=self.case.case_id,
                query=template.query,
                headers=template.headers,
                body=template.body,
                slot_values=slot_values,
                identity_runtime=identity_runtime,
                bootstrap_request=True,
            )
            extracted = {
                extractor.extractor_id: extract_response_value(response, extractor)
                for extractor in template.response_extractors
            }
            bootstrap_outputs[request_or_path.template_id] = extracted
            csrf_slot_id = getattr(identity.binding, "csrf_slot_id", None)
            if csrf_slot_id is not None and csrf_slot_id in extracted:
                extractor = next(
                    item
                    for item in template.response_extractors
                    if item.extractor_id == csrf_slot_id
                )
                identity_runtime.set_csrf(
                    csrf_slot_id,
                    str(extracted[csrf_slot_id]),
                    origin=self.snapshot.target.scope.base_url,
                    max_length=extractor.max_length,
                )
            return response

        identity_runtime.bootstrap(
            send_bootstrap,
            requests=identity.bootstrap_requests,
        )

    def prepare(self) -> None:
        if self._prepared:
            raise RuntimeError("target case session is already prepared")
        if self.context.cancellation_requested():
            raise JiejianError(ErrorCode.EXEC_CANCELLED, "复杂权限执行已取消")
        try:
            # 用实际请求共用的 Guard 在任何身份、恢复或目标网络操作前完成第二道自检。
            self.runtime.guard.authorize_url(
                self.snapshot.target.scope.base_url
            )
        except JiejianError as exc:
            if exc.code == ErrorCode.SELF_TARGET_FORBIDDEN.value:
                self._self_target_blocked = True
            raise
        reset_path = self.snapshot.target.reset_path
        if self.workflow.reset_strategy.kind.value == "RESET_ENDPOINT":
            reset_path = self.workflow.reset_strategy.path
            try:
                self.runtime.adapter.cleanup(reset_path, case_id=self.case.case_id)
            except JiejianError as exc:
                if exc.code == ErrorCode.SELF_TARGET_FORBIDDEN.value:
                    # Guard 在任何网络副作用前拒绝，自检场景没有目标状态需要恢复。
                    self._self_target_blocked = True
                    raise
                raise JiejianError(
                    ErrorCode.PREPARE_RECOVERY_FAILED,
                    "执行前无法恢复到可比较起始状态",
                ) from exc
        elif self.workflow.reset_strategy.kind.value == "UNIQUE_RESOURCE_WORKFLOW":
            if not any(
                step.purpose.value == "CLEANUP" for step in self.workflow.steps
            ):
                raise JiejianError(
                    ErrorCode.BASELINE_INVALID,
                    "唯一资源恢复流程缺少已确认清理步骤",
                )
        else:
            raise JiejianError(
                ErrorCode.BASELINE_INVALID,
                "当前工作流 reset strategy 无可执行恢复器",
            )
        required_identity_ids = {
            (
                self.runtime._subject_identities[self.case.subject_id].identity_id
                if step.identity_id == CASE_SUBJECT_IDENTITY
                else step.identity_id
            )
            for step in self.workflow.steps
        }
        self._identities = {
            identity.identity_id: HttpIdentityRuntime(
                identity.binding,
                resolve_secret=lambda reference: _secret_value(
                    self.context.environ,
                    reference,
                    required=True,
                ),
                business_origin=self.snapshot.target.scope.base_url,
            )
            for identity in self.snapshot.identities
            if identity.identity_id in required_identity_ids
        }
        for identity_id, identity_runtime in self._identities.items():
            try:
                self._bootstrap_identity(identity_id, identity_runtime)
            except JiejianError as exc:
                raise JiejianError(
                    ErrorCode.IDENTITY_PREPARATION_FAILED,
                    "身份准备失败",
                ) from exc
        for step in self._ordered_steps:
            if step.purpose.value != "SETUP":
                continue
            try:
                fact, response = self.runtime.adapter.execute_detailed(
                    step.request_template,
                    case_id=self.case.case_id,
                    action_id=self.case.action_id,
                    classifier=step.classifier,
                    slot_values=self._values_for(step),
                    identity_runtime=self._runtime_for(step),
                )
                if fact.outcome is not ExecutionOutcome.ACCEPTED:
                    raise JiejianError(
                        ErrorCode.SETUP_STEP_FAILED,
                        "SETUP 步骤未被接受",
                    )
                self._outputs[step.id] = {
                    extractor.extractor_id: extract_response_value(
                        response,
                        extractor,
                    )
                    for extractor in step.output_extractors
                }
            except JiejianError as exc:
                if exc.code in {
                    ErrorCode.VALUE_EXTRACTION_FAILED.value,
                    ErrorCode.SECRET_MISSING.value,
                }:
                    raise
                raise JiejianError(
                    ErrorCode.SETUP_STEP_FAILED,
                    "SETUP 步骤失败",
                ) from exc
        self._prepared = True

    def observe_target(
        self,
        spec: ObserverSpec,
        binding: ObserverRequirementBinding,
        correlation: Any,
        phase: ObservationPhase,
    ) -> TargetObservationResult | None:
        if spec.observer_type is not ObserverType.OWNER_API:
            return None
        token = ""
        if binding.identity_id is not None:
            identity = self._identity_definitions[binding.identity_id]
            identity_runtime = HttpIdentityRuntime(
                identity.binding,
                resolve_secret=lambda reference: _secret_value(
                    self.context.environ,
                    reference,
                    required=True,
                ),
                business_origin=self.snapshot.target.scope.base_url,
            )
            self._bootstrap_identity(binding.identity_id, identity_runtime)
        else:
            token = _secret_value(
                self.context.environ,
                binding.credential_ref or "",
                required=True,
            ) or ""
            identity_runtime = HttpIdentityRuntime(
                BearerIdentityBinding(secret_ref=binding.credential_ref or ""),
                resolve_secret=lambda reference: _secret_value(
                    self.context.environ,
                    reference,
                    required=True,
                ),
                business_origin=self.snapshot.target.scope.base_url,
            )
        try:
            envelope = OwnerApiObserverAdapter(
                spec=spec,
                utc_now_us=self.context.clock,
            ).observe(
                self.runtime.adapter,
                resource_id=correlation.resource_id,
                owner_token=token,
                case_id=correlation.case_id,
                phase=phase,
                known_secrets=tuple(value for value in (token,) if value),
                identity_runtime=identity_runtime,
            )
            return TargetObservationResult(
                envelope=envelope,
                outcome=evaluate_observer_outcome(
                    envelope,
                    required=spec.required,
                ),
            )
        finally:
            identity_runtime.close()

    def evaluate_baseline(
        self,
        baseline_envelopes: tuple[ObservationEnvelope, ...],
        *,
        ignored_case_fields: tuple[str, ...] = (),
    ) -> TargetBaselineResult:
        """构造完整基线指纹，并只忽略差分计划明确声明的 Case 字段。"""

        if not self.workflow.baseline_projections:
            return TargetBaselineResult(
                valid=False,
                comparison_fingerprints=(),
                reason_codes=("BASELINE_INTEGRITY_INVALID",),
            )
        relationship_payload = self.case.model_dump(
            mode="json",
            include={"subject_id", "relation_paths", "context"},
        )
        for field_name in ignored_case_fields:
            relationship_payload.pop(field_name, None)
        relationship_fingerprint = hashlib.sha256(
            _json_bytes(relationship_payload)
        ).hexdigest()
        integrities: list[Any] = []
        comparison_fingerprints: list[str] = []
        for projection in self.workflow.baseline_projections:
            for resource_id in self.case.resource_ids:
                envelope = next(
                    (
                        item
                        for item in baseline_envelopes
                        if item.correlation.resource_id == resource_id
                        and item.state is not None
                    ),
                    None,
                )
                if envelope is None or envelope.state is None:
                    return TargetBaselineResult(
                        valid=False,
                        comparison_fingerprints=(),
                        reason_codes=("BASELINE_OBSERVATION_INCOMPLETE",),
                    )
                fingerprint = build_baseline_fingerprint(
                    logical_resource_handle=projection.logical_resource_handle,
                    normalized_resource_state=envelope.state.canonical_sha256,
                    workflow_state=self.workflow.workflow_fingerprint or "",
                    relationship_projection=relationship_fingerprint,
                    effect_projection=hashlib.sha256(
                        _json_bytes(self.action.model_dump(mode="json"))
                    ).hexdigest(),
                    normalization_version=projection.normalization_version,
                    projection_version=projection.projection_version,
                )
                valid = (
                    projection.expected_fingerprint is None
                    or projection.expected_fingerprint == fingerprint.fingerprint
                )
                integrities.append(
                    {
                        "mode": projection.integrity_mode,
                        "expected_fingerprint": projection.expected_fingerprint,
                        "observed_fingerprint": fingerprint.fingerprint,
                        "valid": valid,
                        "reason_codes": (
                            ()
                            if valid
                            else ("BASELINE_FINGERPRINT_MISMATCH",)
                        ),
                    }
                )
                comparison_fingerprints.append(fingerprint.fingerprint)
        stable_fingerprints = tuple(sorted(set(comparison_fingerprints)))
        self.runtime.baseline_integrities[self.case.case_id] = tuple(integrities)
        if not all(item["valid"] for item in integrities):
            return TargetBaselineResult(
                valid=False,
                comparison_fingerprints=stable_fingerprints,
                reason_codes=("BASELINE_INTEGRITY_INVALID",),
            )
        return TargetBaselineResult(
            valid=True,
            comparison_fingerprints=stable_fingerprints,
        )

    def execute_target(self) -> ExecutionFact:
        if not self._prepared:
            raise RuntimeError("target case session is not prepared")
        if self._target_executed:
            raise RuntimeError("TARGET already executed for this case session")
        self._target_executed = True
        target = next(
            step
            for step in self._ordered_steps
            if step.id == self.workflow.target_step_id
        )
        try:
            execution, response = self.runtime.adapter.execute_detailed(
                target.request_template,
                case_id=self.case.case_id,
                action_id=self.case.action_id,
                classifier=target.classifier,
                slot_values=self._values_for(target),
                identity_runtime=self._runtime_for(target),
            )
        except JiejianError as exc:
            if exc.code not in {
                ErrorCode.TARGET_UNREACHABLE.value,
                ErrorCode.EXEC_TIMEOUT.value,
                ErrorCode.EXEC_REQUEST.value,
            }:
                raise
            raise JiejianError(
                ErrorCode.TARGET_EXECUTION_FAILED,
                "TARGET 请求失败",
            ) from exc
        if execution.outcome is ExecutionOutcome.FAILED:
            raise JiejianError(
                ErrorCode.TARGET_EXECUTION_FAILED,
                "TARGET 请求失败",
            )
        self._outputs[target.id] = {
            extractor.extractor_id: extract_response_value(response, extractor)
            for extractor in target.output_extractors
        }
        self._execution = execution
        self._response = response
        return execution

    def resolve_execution(
        self,
        observations: tuple[ObservationEnvelope, ...],
    ) -> ExecutionFact:
        if self._execution is None or self._response is None:
            raise RuntimeError("TARGET response is not available")
        target = next(
            step
            for step in self._ordered_steps
            if step.id == self.workflow.target_step_id
        )
        self._execution = _apply_terminal_completion(
            self._execution,
            self._response,
            target.classifier,
            completion_bindings=self._bindings,
            observations=observations,
            case_id=self.case.case_id,
        )
        return self._execution

    def build_disclosure_proof(
        self,
        effect: SecurityEffectDefinition,
        resource_id: str,
        observations: tuple[ObservationEnvelope, ...],
    ) -> DisclosureProof | None:
        if effect.kind.value != "DATA_DISCLOSURE":
            return None
        binding = self.runtime._effect_bindings[effect.effect_id]
        baseline = next(
            (
                item
                for item in observations
                if item.phase is ObservationPhase.BASELINE
                and item.correlation.resource_id == resource_id
                and item.state is not None
                and item.observer_id
                in {
                    self._bindings[requirement].observer_id
                    for requirement in binding.required_channels
                }
            ),
            None,
        )
        owner_value = (
            baseline.state.canonical_data
            if baseline is not None and baseline.state is not None
            else None
        )
        response_value = self._response.data if self._response is not None else None
        owner_projection, owner_complete = _project_fields(
            owner_value,
            effect.protected_fields,
            require_present=True,
        )
        response_projection, response_complete = _project_fields(
            response_value,
            effect.protected_fields,
            require_present=False,
        )
        owner_digest = hmac.new(
            self.runtime._disclosure_key,
            _json_bytes(owner_projection),
            hashlib.sha256,
        ).hexdigest()
        response_digest = hmac.new(
            self.runtime._disclosure_key,
            _json_bytes(response_projection),
            hashlib.sha256,
        ).hexdigest()
        complete = owner_complete and response_complete
        return DisclosureProof(
            projection_version=binding.projection_version,
            projection_complete=complete,
            owner_digest=owner_digest,
            response_digest=response_digest,
            matched=complete and hmac.compare_digest(owner_digest, response_digest),
            correlation_digest=hashlib.sha256(
                f"{self.case.case_id}:{resource_id}".encode("utf-8")
            ).hexdigest(),
        )

    def cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        if self._self_target_blocked:
            return
        issues: list[TargetCleanupIssue] = []
        for step in reversed(self._ordered_steps):
            if step.purpose.value != "CLEANUP":
                continue
            try:
                fact, _ = self.runtime.adapter.execute_detailed(
                    step.request_template,
                    case_id=self.case.case_id,
                    action_id=self.case.action_id,
                    classifier=step.classifier,
                    slot_values=self._values_for(step),
                    identity_runtime=self._runtime_for(step),
                    cleanup_request=True,
                )
                if fact.outcome is not ExecutionOutcome.ACCEPTED:
                    raise JiejianError(
                        ErrorCode.RECOVERY_UNAVAILABLE,
                        "已确认恢复请求未被目标接受",
                    )
            except Exception as exc:
                issues.append(
                    TargetCleanupIssue(
                        CleanupIssueCode.POST_CASE_RECOVERY_FAILED,
                        _safe_error_code(exc),
                    )
                )
        if self.workflow.reset_strategy.kind.value == "RESET_ENDPOINT":
            try:
                self.runtime.adapter.cleanup(
                    self.workflow.reset_strategy.path,
                    case_id=self.case.case_id,
                )
            except Exception as exc:
                issues.append(
                    TargetCleanupIssue(
                        CleanupIssueCode.POST_CASE_RECOVERY_FAILED,
                        _safe_error_code(exc),
                    )
                )
        for identity_runtime in self._identities.values():
            try:
                identity_runtime.close()
            except Exception as exc:
                issues.append(
                    TargetCleanupIssue(
                        CleanupIssueCode.IDENTITY_CLOSE_FAILED,
                        _safe_error_code(exc),
                    )
                )
        if issues:
            # 同类问题只保留首个安全原因，避免重复身份或步骤放大 wire。
            unique: dict[CleanupIssueCode, TargetCleanupIssue] = {}
            for item in issues:
                unique.setdefault(item.code, item)
            raise TargetCleanupError(tuple(unique.values()))


def _safe_error_code(exc: Exception) -> str | None:
    """仅提取稳定 JiejianError code，不把异常消息带入结果。"""

    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, JiejianError):
            return current.code
        current = current.__cause__
    return None
