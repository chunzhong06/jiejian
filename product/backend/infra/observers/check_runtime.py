# 当前检查的真实 Observer 桥：逐 Case 保留来源与阶段，复用有界适配器，不重放其他 Case 观察。
from __future__ import annotations

import time
import secrets
from dataclasses import dataclass
from pathlib import Path

from product.backend.core.check_plan import classify_http_resource_presence
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.observers.coordinator import ObserverCoordinator, default_observer_registry
from product.backend.infra.observers.effect_projector import EffectProjector, _target_projection
from product.backend.infra.observers.owner_api import OwnerApiObserverAdapter
from product.protocols.check_result import CheckObservation
from product.protocols.check_runtime import CheckProofConfig, CheckRuntimeBundle
from product.protocols.execution_v3 import EffectProofRequirement, ExecutionCase
from product.protocols.observer import (CausalityStatus, Correlation, ObservationCompleteness,
    ObservationEnvelope, ObservationPhase, ObserverOutcome, ObserverOutcomeStatus, ObserverType)


@dataclass(frozen=True)
class CheckObservedSource:
    observation: CheckObservation
    # 仅在 Runner 内比较受保护业务投影；原始响应/状态不得进入发布文件。
    baseline_projection: tuple | None
    execution_completed: bool = False
    completion_case_id: str | None = None
    completion_resource_id: str | None = None
    completion_binding_fingerprint: str | None = None


@dataclass(frozen=True)
class _TargetObservation:
    envelope: ObservationEnvelope
    outcome: ObserverOutcome


class _OwnerObservationSession:
    def __init__(self, owner, proof, *, cleanup):
        self.owner, self.proof, self.cleanup = owner, proof, cleanup

    def observe_target(self, spec, _binding, correlation, phase):
        with self.owner.web.identity_session(self.proof.observation_identity_id) as identity:
            # 清理观察仍走同一适配器的恢复预留；不另建不受控 HTTP 客户端。
            executor = _RecoveryAwareAdapter(self.owner.web.adapter, self.cleanup)
            envelope = OwnerApiObserverAdapter(spec, self.owner.clock).observe(executor,
                resource_id=correlation.resource_id, owner_token="", case_id=correlation.case_id,
                phase=phase, identity_runtime=identity, known_secrets=self.owner.known_secrets,
                request_marker=correlation.request_marker)
        complete = envelope.completeness is ObservationCompleteness.COMPLETE
        return _TargetObservation(envelope, ObserverOutcome(observer_id=spec.observer_id, required=spec.required,
            status=ObserverOutcomeStatus.AVAILABLE if complete else ObserverOutcomeStatus.INCONCLUSIVE,
            reason_codes=() if complete else ("REQUIRED_OBSERVER_INCOMPLETE",)))


class _RecoveryAwareAdapter:
    def __init__(self, adapter, cleanup):
        self.adapter, self.cleanup = adapter, cleanup

    def request(self, *args, **kwargs):
        return self.adapter.request(*args, **kwargs, cleanup_request=self.cleanup)


class CheckObserverRuntime:
    """每个 Case 与 proof 拥有独立游标、包络历史及身份确认；无跨 Case 观察缓存。"""

    def __init__(self, bundle: CheckRuntimeBundle, web, *, attempt_dir: Path, environ,
                 cancellation_requested, clock_us=None):
        self.bundle, self.web = bundle, web
        self.clock = clock_us or (lambda: time.time_ns() // 1000)
        self.cancelled = cancellation_requested
        self.specs = {item.observer_id: item for item in bundle.observers}
        from product.backend.infra.execution.web.check_runtime import check_secret_names
        self.known_secrets = tuple(environ[name] for name in check_secret_names(bundle) if environ.get(name))
        self.coordinator = ObserverCoordinator(registry=default_observer_registry(), specs=self.specs,
            bindings={}, environ=environ, attempt_dir=attempt_dir, clock=self.clock,
            cancellation_requested=cancellation_requested)
        self._envelopes = {}
        self._cursors = {}
        self._disclosure_key = secrets.token_bytes(32)
        self._trusted_histories = {}

    def restart_case_baseline(self, case_id: str) -> None:
        """恢复后的前置观察重新建窗；已返回的证据保留，内部投影不跨恢复动作拼接。"""
        for collection in (self._envelopes, self._cursors, self._trusted_histories):
            for key in tuple(collection):
                if key[0] == case_id:
                    del collection[key]

    def observe(self, *, case: ExecutionCase, action_id: str, requirement: EffectProofRequirement,
                proof: CheckProofConfig, phase: str, baseline_trusted: bool, cleanup=False) -> CheckObservedSource:
        """执行一次冻结来源，错误只形成 UNKNOWN；取消会在非恢复路径继续向上抛出。"""
        started = self.clock()
        observer_id = proof.observer_id or "recorded-" + proof.binding_fingerprint[:32]
        common = dict(effect_id=proof.effect_id, proof_fingerprint=requirement.proof_fingerprint,
            observer_id=observer_id, level=requirement.level, phase=phase, window_start_us=started)
        key = (case.case_id, proof.binding_fingerprint, proof.observer_id)
        previous_trust = self._trusted_histories.get(key, True)
        # 本轮未完成即视为链路缺口；早退或适配器异常不能保留前一轮的完整标记。
        if phase in ("AFTER", "EVENTUAL"):
            self._trusted_histories[key] = False
        try:
            if (proof.effect_id, proof.binding_fingerprint, proof.rule) != (
                requirement.effect_id, requirement.binding_fingerprint, requirement.rule
            ) or requirement.resource_id != case.resource_id:
                return self._unknown(common, "OBSERVER_CORRELATION_INVALID")
            if self.cancelled() and not cleanup:
                raise JiejianError(ErrorCode.EXEC_CANCELLED, "复杂权限执行已取消")
            source_identity = self.web.verify_identity(proof.observation_identity_id, case, cleanup=cleanup)
            if proof.rule != "REGISTERED_EFFECT":
                response = self.web.request(proof.request, case=case, action_id=action_id,
                    identity_id=proof.observation_identity_id, cleanup=cleanup)
                state, closure = classify_http_resource_presence(response.status_code, same_resource=True, same_run=True)
                if proof.rule == "RECORDED_SUPPORT":
                    state, closure = "UNKNOWN", "OPEN"
                complete = state != "UNKNOWN"
                correlated = source_identity == "MATCH" and proof.exclusive_resource_window and (
                    baseline_trusted or phase in ("BASELINE", "BEFORE", "RECOVERY"))
                observation = CheckObservation(**common, state=state, closure=closure, complete=complete,
                    reliable=source_identity == "MATCH", correlated=correlated,
                    authoritative=proof.rule == "HTTP_RESOURCE_PRESENCE", window_end_us=self.clock(),
                    correlation_refs=(case.case_id, self.web.request_marker(case.case_id)), reason_codes=() if complete and correlated else ("OBSERVATION_UNINTERPRETED",))
                projection = (case.resource_id, state) if complete and source_identity == "MATCH" else None
                return CheckObservedSource(observation, projection)
            spec = self.specs[proof.observer_id]
            actual_phase = ObservationPhase.BEFORE if phase in ("BASELINE", "BEFORE") else ObservationPhase.AFTER if phase == "RECOVERY" else ObservationPhase(phase)
            if actual_phase not in spec.phases:
                return self._unknown(common, "OBSERVER_PHASE_UNAVAILABLE")
            correlation = Correlation(case_id=case.case_id, resource_id=case.resource_id, request_marker=self.web.request_marker(case.case_id))
            key = (case.case_id, proof.binding_fingerprint, proof.observer_id)
            session = _OwnerObservationSession(self, proof, cleanup=cleanup)
            envelope, outcome, cursors = self.coordinator.observe_one(session, spec, spec, correlation,
                actual_phase, self._cursors.get(key, ()))
            # 审计后置阶段均从同一 BEFORE 锚点读取完整 TARGET 窗口。
            # 推进到 AFTER 尾部会让 EVENTUAL 只读到空尾段，丢掉已成立的因果链；
            # 重读仍受原游标前缀校验与扫描预算约束，不把 TAG_NOT_FOUND 当成完整事实。
            if spec.observer_type is not ObserverType.STRUCTURED_AUDIT_LOG or phase in ("BASELINE", "BEFORE"):
                self._cursors[key] = cursors
            if envelope is None:
                return self._unknown(common, "REQUIRED_OBSERVER_INCOMPLETE")
            if (envelope.observer_id, envelope.observer_type, envelope.phase, envelope.target_id, envelope.correlation) != (
                spec.observer_id, spec.observer_type, actual_phase, spec.target.target_id, correlation
            ):
                return self._unknown(common, "OBSERVER_CORRELATION_INVALID")
            history = self._envelopes.setdefault(key, [])
            # 恢复观察只与本次原始 baseline 比较，不把恢复后不存在覆盖已确认禁止效果。
            if phase != "RECOVERY":
                history.append(envelope)
            trusted = source_identity == "MATCH" and outcome.status is ObserverOutcomeStatus.AVAILABLE and (
                envelope.completeness is ObservationCompleteness.COMPLETE and envelope.causality is CausalityStatus.CORRELATED)
            if phase in ("AFTER", "EVENTUAL"):
                self._trusted_histories[key] = previous_trust and trusted
            target_state = spec.observer_type in (ObserverType.OWNER_API, ObserverType.READ_ONLY_SQLITE, ObserverType.AZURE_BLOB_OBJECT)
            projection = _target_projection(spec.observer_type, envelope.state.canonical_data, case.resource_id) if (
                trusted and target_state and envelope.state is not None) else None
            disclosure = None
            if proof.effect_kind == "DATA_DISCLOSURE" and spec.observer_type is ObserverType.OWNER_API:
                from product.backend.infra.observers.check_disclosure import disclosure_proof
                baseline_envelope = history[0] if history else None
                owner = baseline_envelope.state.canonical_data.get("data") if baseline_envelope is not None and baseline_envelope.state is not None else None
                response = self.web.target_response(case.case_id)
                disclosure = disclosure_proof(owner=owner, response=response.data if response is not None else None,
                    fields=proof.protected_projection, key=self._disclosure_key, marker=self.web.request_marker(case.case_id))
                # 合法读取的受保护字段摘要是披露检查的基线，不要求响应另含业务 state 字段。
                current_owner = envelope.state.canonical_data.get("data") if envelope.state is not None else None
                baseline_proof = disclosure_proof(owner=current_owner, response=current_owner, fields=proof.protected_projection,
                    key=self._disclosure_key, marker=self.web.request_marker(case.case_id))
                projection = (case.resource_id, baseline_proof.owner_digest) if trusted and baseline_proof.projection_complete else None
            elif projection is not None and projection[1] is None and spec.observer_type is ObserverType.OWNER_API:
                # 对象响应缺少业务状态不是资源不存在；现有投影器的空值不能充当可信基线。
                projection = None
            fact = EffectProjector.project_check(case_id=case.case_id, resource_id=case.resource_id,
                proof=proof, spec=spec, envelopes=tuple(history) if phase != "RECOVERY" else (envelope,), disclosure_proof=disclosure)
            correlated = trusted and (not target_state or (proof.exclusive_resource_window and (
                baseline_trusted or phase in ("BASELINE", "BEFORE", "RECOVERY"))))
            observation = CheckObservation(**common, state=fact.effect.value, closure=fact.temporal_closure.value,
                complete=fact.complete and trusted, reliable=fact.reliable and trusted,
                correlated=fact.correlated and correlated, authoritative=True, window_end_us=self.clock(),
                correlation_refs=(case.case_id, self.web.request_marker(case.case_id)), reason_codes=fact.reason_codes)
            # 非状态来源以完整规范通道的初始状态为基线；不把 task/queue 的 lineage 当业务效果。
            if trusted and not target_state and phase in ("BASELINE", "BEFORE"):
                projection = (case.resource_id, "CHANNEL_READY")
            terminal = (trusted and phase == "EVENTUAL" and spec.observer_type is ObserverType.ASYNC_TASK_STATUS
                and envelope.state is not None and envelope.state.canonical_data.get("task_state") == "SUCCESS"
                and isinstance(envelope.state.canonical_data.get("task_id"), str)
                and bool(envelope.state.canonical_data["task_id"]))
            # 私有执行完成事实单独绑定 Case/资源/proof，不把任务结果投影为 ZIP 效果。
            return CheckObservedSource(observation, projection, terminal,
                case.case_id if terminal else None, case.resource_id if terminal else None,
                proof.binding_fingerprint if terminal else None)
        except JiejianError as exc:
            if exc.code == ErrorCode.EXEC_CANCELLED.value and not cleanup:
                raise
            return self._unknown(common, "REQUIRED_OBSERVER_INCOMPLETE")
        except (ValueError, TypeError, KeyError):
            return self._unknown(common, "OBSERVER_CORRELATION_INVALID")

    def _unknown(self, common, reason):
        return CheckObservedSource(CheckObservation(**common, state="UNKNOWN", closure="UNKNOWN",
            complete=False, reliable=False, correlated=False, authoritative=False,
            window_end_us=self.clock(), reason_codes=(reason,)), None)

    def trace(self, action, case):
        from product.backend.infra.observers.check_trace import build_check_trace
        sources = [(proof, source) for proof in action.proofs for source in proof.auxiliary_sources
                   if source.trace_namespace is not None]
        if not sources:
            return None
        identity = next(item for item in self.bundle.identities if item.identity_id == case.subject_test_identity_id)
        namespaces = {source.trace_namespace for _, source in sources}
        mapped = identity.verification if identity.verification is not None and identity.verification.namespace in namespaces and len(namespaces) == 1 else None
        groups = []
        for proof, source in sources:
            key = (case.case_id, proof.binding_fingerprint, source.observer_id)
            groups.append((tuple(self._envelopes.get(key, ())), self._trusted_histories.get(key, False)))
        return build_check_trace(case=case, action_id=action.action_id,
            planned_subject_id=mapped.expected_application_subject_id if mapped is not None else case.subject_test_identity_id,
            marker=self.web.request_marker(case.case_id), groups=groups)
