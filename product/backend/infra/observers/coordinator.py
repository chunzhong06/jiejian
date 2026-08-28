# =============================================================================
# 共享 Observer 阶段协调器
#
# 定位
#   在通用 Runner 与 Observer Adapter、Target Case Session 之间调度观察。
#
# 职责
#   维护阶段游标｜校验相关性｜归一化 Observer Outcome｜投影 ObservationFact。
#
# 边界
#   不认识 Web/HTTP/身份协议；OWNER_API 必须通过 TargetCaseSession.observe_target。
# =============================================================================

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.verification.facts import ObservationFact, ObservedEffect, TemporalClosure
from product.backend.infra.execution.port import TargetCaseSession
from product.backend.infra.observers.async_task import run_async_task_observer
from product.backend.infra.observers.audit_log import run_audit_log_observer
from product.backend.infra.observers.azure_blob import run_azure_blob_observer
from product.backend.infra.observers.azure_queue import run_azure_queue_observer
from product.backend.infra.observers.registry import ObserverRegistry
from product.backend.infra.observers.sqlite import run_sqlite_observer
from product.protocols import AuditLogStartCursor, CausalityStatus, Correlation, ObservationCompleteness, ObservationEnvelope, ObservationPhase, ObserverOutcome, ObserverOutcomeStatus, ObserverSpec, ObserverType


_PHASE_ORDER = {ObservationPhase.BASELINE: 0, ObservationPhase.BEFORE: 1, ObservationPhase.AFTER: 2, ObservationPhase.EVENTUAL: 3}


def _failure(spec: ObserverSpec, code: str | None = None) -> ObserverOutcome:
    reason = code or ("REQUIRED_OBSERVER_INCOMPLETE" if spec.required else "SUPPORTING_OBSERVER_INCOMPLETE")
    return ObserverOutcome(observer_id=spec.observer_id, required=spec.required, status=ObserverOutcomeStatus.INCONCLUSIVE, reason_codes=(reason,))


def _aggregate(current: ObserverOutcome | None, incoming: ObserverOutcome) -> ObserverOutcome:
    if current is None:
        return incoming
    statuses = {current.status, incoming.status}
    status = ObserverOutcomeStatus.EXECUTION_ERROR if ObserverOutcomeStatus.EXECUTION_ERROR in statuses else ObserverOutcomeStatus.INCONCLUSIVE if ObserverOutcomeStatus.INCONCLUSIVE in statuses else ObserverOutcomeStatus.AVAILABLE
    return ObserverOutcome(observer_id=current.observer_id, required=current.required, status=status, reason_codes=tuple(sorted(set((*current.reason_codes, *incoming.reason_codes)))))


class ObserverCoordinator:
    """按 Case/资源/阶段顺序运行共享 Observer，并保留审计游标。"""

    def __init__(self, *, registry: ObserverRegistry, specs: Mapping[str, ObserverSpec], bindings: Mapping[str, Any], environ: Mapping[str, str], attempt_dir: Path, clock, cancellation_requested) -> None:
        self.registry = registry
        self.specs = specs
        self.bindings = bindings
        self.environ = environ
        self.attempt_dir = attempt_dir
        self.clock = clock
        self.cancellation_requested = cancellation_requested

    def observe_one(self, session: TargetCaseSession, binding: Any, spec: ObserverSpec, correlation: Correlation, phase: ObservationPhase, cursors: tuple[AuditLogStartCursor, ...]) -> tuple[ObservationEnvelope | None, ObserverOutcome, tuple[AuditLogStartCursor, ...]]:
        if spec.observer_type is ObserverType.OWNER_API:
            result = session.observe_target(spec, binding, correlation, phase)
            if result is None:
                return None, _failure(spec, "OBSERVER_UNSUPPORTED"), cursors
            return result.envelope, result.outcome, cursors
        executor = self.registry.get(spec.observer_type)
        if executor is None:
            return None, _failure(spec, "OBSERVER_UNSUPPORTED"), cursors
        kwargs = {"attempt_dir": self.attempt_dir, "parent_environ": self.environ}
        if spec.observer_type is ObserverType.STRUCTURED_AUDIT_LOG:
            result = executor(spec, correlation, phase, start_cursors=cursors, **kwargs)
        else:
            result = executor(spec, correlation, phase, **kwargs)
        next_cursors = cursors
        envelope = result.envelope
        if spec.observer_type is ObserverType.STRUCTURED_AUDIT_LOG and envelope is not None and envelope.state is not None:
            try:
                next_cursors = tuple(AuditLogStartCursor.model_validate(item) for item in envelope.state.canonical_data.get("next_offsets", ()))
            except (TypeError, ValueError, ValidationError):
                return envelope, _failure(spec, "OBSERVER_CURSOR_INVALID"), cursors
        return envelope, result.outcome, next_cursors

    def observe_phase(
        self,
        session: TargetCaseSession,
        case: Any,
        phase: ObservationPhase,
        envelopes: list[ObservationEnvelope],
        outcomes: dict[str, ObserverOutcome],
        cursors: dict[tuple[str, str], tuple[AuditLogStartCursor, ...]],
        *,
        requirements_to_run: tuple[str, ...] | None = None,
        required_requirements: tuple[str, ...] | None = None,
    ) -> bool:
        requirements = requirements_to_run or tuple(case.required_observations)
        required = set(required_requirements or case.required_observations)
        unavailable = False
        for resource_id in case.resource_ids:
            for requirement in requirements:
                binding = self.bindings[requirement]
                if phase not in binding.phases:
                    continue
                spec = self.specs[binding.observer_id]
                correlation = Correlation(case_id=case.case_id, resource_id=resource_id, request_marker=case.case_id)
                envelope, outcome, next_cursor = self.observe_one(session, binding, spec, correlation, phase, cursors.get((requirement, resource_id), ()))
                outcomes[spec.observer_id] = _aggregate(outcomes.get(spec.observer_id), outcome)
                cursors[(requirement, resource_id)] = next_cursor
                if envelope is not None:
                    envelopes.append(envelope)
                unavailable = unavailable or (
                    requirement in required
                    and outcome.status is not ObserverOutcomeStatus.AVAILABLE
                )
                if self.cancellation_requested():
                    raise JiejianError(ErrorCode.EXEC_CANCELLED, "复杂权限执行已取消")
        return unavailable

    def complete_required_outcomes(
        self,
        case: Any,
        outcomes: tuple[ObserverOutcome, ...],
        *,
        requirements_to_run: tuple[str, ...] | None = None,
    ) -> tuple[ObserverOutcome, ...]:
        """补齐本次实际运行集合的观察结果，并保留关键与佐证角色。"""

        completed = {item.observer_id: item for item in outcomes}
        requirements = requirements_to_run or tuple(case.required_observations)
        required = set(case.required_observations)
        for requirement_id in requirements:
            observer_id = self.bindings[requirement_id].observer_id
            if observer_id not in completed:
                is_required = requirement_id in required
                completed[observer_id] = ObserverOutcome(
                    observer_id=observer_id,
                    required=is_required,
                    status=ObserverOutcomeStatus.INCONCLUSIVE,
                    reason_codes=(
                        "REQUIRED_OBSERVER_INCOMPLETE"
                        if is_required
                        else "SUPPORTING_OBSERVER_INCOMPLETE",
                    ),
                )
        return tuple(completed.values())

    def project_facts(
        self,
        case: Any,
        envelopes: tuple[ObservationEnvelope, ...],
        *,
        requirements_to_run: tuple[str, ...] | None = None,
        required_requirements: tuple[str, ...] | None = None,
    ) -> tuple[ObservationFact, ...]:
        """按冻结的 Observer 类型语义把规范化 Envelope 投影为纯事实。"""

        facts: list[ObservationFact] = []
        requirements = requirements_to_run or tuple(case.required_observations)
        required = set(required_requirements or case.required_observations)
        for requirement_id in requirements:
            binding = self.bindings[requirement_id]
            for resource_id in case.resource_ids:
                selected = tuple(
                    sorted(
                        (
                            item
                            for item in envelopes
                            if item.observer_id == binding.observer_id
                            and item.observer_type is binding.observer_type
                            and item.correlation.case_id == case.case_id
                            and item.correlation.resource_id == resource_id
                        ),
                        key=lambda item: _PHASE_ORDER[item.phase],
                    )
                )
                facts.append(
                    self._project_fact(
                        requirement_id,
                        resource_id,
                        binding,
                        selected,
                        required=requirement_id in required,
                    )
                )
        return tuple(facts)

    @staticmethod
    def _project_fact(
        requirement_id: str,
        resource_id: str,
        binding: Any,
        selected: tuple[ObservationEnvelope, ...],
        *,
        required: bool,
    ) -> ObservationFact:
        trustworthy = bool(selected) and all(
            item.completeness is ObservationCompleteness.COMPLETE
            and item.causality is CausalityStatus.CORRELATED
            and item.state is not None
            for item in selected
        )
        if not trustworthy:
            return _unknown_fact(
                requirement_id,
                resource_id,
                reason=(
                    "REQUIRED_OBSERVER_INCOMPLETE"
                    if required
                    else "SUPPORTING_OBSERVER_INCOMPLETE"
                ),
            )

        phases = {item.phase for item in selected}
        if binding.observer_type in {
            ObserverType.ASYNC_TASK_STATUS,
            ObserverType.AZURE_QUEUE_PEEK,
        } and set(binding.phases) == {ObservationPhase.EVENTUAL}:
            closed = ObservationPhase.EVENTUAL in phases
        else:
            closed = ObservationPhase.AFTER in phases and (
                ObservationPhase.EVENTUAL not in binding.phases
                or ObservationPhase.EVENTUAL in phases
            )
        closure = TemporalClosure.CLOSED if closed else TemporalClosure.OPEN
        states = tuple(item.state for item in selected if item.state is not None)
        observer_type = binding.observer_type

        if observer_type in {
            ObserverType.OWNER_API,
            ObserverType.READ_ONLY_SQLITE,
            ObserverType.AZURE_BLOB_OBJECT,
        }:
            comparable = len(states) >= 2
            changed = comparable and (
                states[0].canonical_sha256 != states[-1].canonical_sha256
            )
            if changed:
                return _known_fact(
                    requirement_id,
                    resource_id,
                    ObservedEffect.CONFIRMED,
                    closure,
                )
            if comparable and closed:
                return _known_fact(
                    requirement_id,
                    resource_id,
                    ObservedEffect.ABSENT,
                    closure,
                )
            return _unknown_fact(
                requirement_id,
                resource_id,
                reason="TEMPORAL_WINDOW_OPEN",
                closure=TemporalClosure.OPEN,
                reliable=True,
                correlated=True,
            )

        if observer_type is ObserverType.STRUCTURED_AUDIT_LOG:
            record_groups = tuple(
                state.canonical_data.get("records")
                if isinstance(state.canonical_data, Mapping)
                else None
                for state in states
            )
            interpretable = all(
                isinstance(group, (list, tuple))
                and all(isinstance(record, Mapping) for record in group)
                for group in record_groups
            )
            records = tuple(
                record
                for group in record_groups
                if isinstance(group, (list, tuple))
                for record in group
            )
            applied = interpretable and any(
                record.get("event_type") == "SIDE_EFFECT"
                and record.get("effect") == "APPLIED"
                for record in records
            )
            if applied:
                return _known_fact(
                    requirement_id,
                    resource_id,
                    ObservedEffect.CONFIRMED,
                    closure,
                )
            if interpretable and closed:
                return _known_fact(
                    requirement_id,
                    resource_id,
                    ObservedEffect.ABSENT,
                    closure,
                )
            return _unknown_fact(
                requirement_id,
                resource_id,
                reason=(
                    "TEMPORAL_WINDOW_OPEN"
                    if interpretable and not closed
                    else "OBSERVATION_UNINTERPRETED"
                ),
                closure=closure,
                reliable=interpretable,
                correlated=True,
            )

        data = states[-1].canonical_data
        if observer_type is ObserverType.ASYNC_TASK_STATUS:
            if not closed:
                return _unknown_fact(
                    requirement_id,
                    resource_id,
                    reason="OBSERVATION_UNINTERPRETED",
                    closure=TemporalClosure.OPEN,
                    reliable=True,
                    correlated=True,
                )
            if isinstance(data, Mapping):
                final_result = data.get("final_result")
                if (
                    data.get("task_state") == "SUCCESS"
                    and isinstance(final_result, Mapping)
                    and final_result.get("effect") == "APPLIED"
                ):
                    return _known_fact(
                        requirement_id,
                        resource_id,
                        ObservedEffect.CONFIRMED,
                        closure,
                    )
                if data.get("task_state") == "NOT_CREATED":
                    return _known_fact(
                        requirement_id,
                        resource_id,
                        ObservedEffect.ABSENT,
                        closure,
                    )
            return _unknown_fact(
                requirement_id,
                resource_id,
                reason="OBSERVATION_UNINTERPRETED",
                closure=closure,
                correlated=True,
            )

        if observer_type is ObserverType.AZURE_QUEUE_PEEK and isinstance(data, Mapping):
            messages = data.get("messages")
            matched_count = data.get("matched_count")
            if (
                isinstance(matched_count, int)
                and not isinstance(matched_count, bool)
                and matched_count > 0
                and isinstance(messages, list)
                and messages
            ):
                return _known_fact(
                    requirement_id,
                    resource_id,
                    ObservedEffect.CONFIRMED,
                    closure,
                )
            if (
                closed
                and data.get("window_complete") is True
                and matched_count == 0
                and messages == []
            ):
                return _known_fact(
                    requirement_id,
                    resource_id,
                    ObservedEffect.ABSENT,
                    closure,
                )
            return _unknown_fact(
                requirement_id,
                resource_id,
                reason="OBSERVATION_WINDOW_INCOMPLETE",
                closure=(
                    TemporalClosure.OPEN
                    if not closed or data.get("window_complete") is not True
                    else closure
                ),
                correlated=True,
            )

        return _unknown_fact(
            requirement_id,
            resource_id,
            reason="OBSERVATION_UNINTERPRETED",
            closure=closure,
            correlated=True,
        )


def _known_fact(
    requirement_id: str,
    resource_id: str,
    effect: ObservedEffect,
    closure: TemporalClosure,
) -> ObservationFact:
    return ObservationFact(
        requirement_id=requirement_id,
        resource_id=resource_id,
        effect=effect,
        complete=True,
        reliable=True,
        correlated=True,
        temporal_closure=closure,
        reason_codes=()
        if closure is TemporalClosure.CLOSED
        else ("TEMPORAL_WINDOW_OPEN",),
    )


def _unknown_fact(
    requirement_id: str,
    resource_id: str,
    *,
    reason: str,
    closure: TemporalClosure = TemporalClosure.UNKNOWN,
    reliable: bool = False,
    correlated: bool = False,
) -> ObservationFact:
    return ObservationFact(
        requirement_id=requirement_id,
        resource_id=resource_id,
        effect=ObservedEffect.UNKNOWN,
        complete=False,
        reliable=reliable,
        correlated=correlated,
        temporal_closure=closure,
        reason_codes=(reason,),
    )


def default_observer_registry() -> ObserverRegistry:
    registry = ObserverRegistry()
    registry.register(ObserverType.READ_ONLY_SQLITE, run_sqlite_observer)
    registry.register(ObserverType.STRUCTURED_AUDIT_LOG, run_audit_log_observer)
    registry.register(ObserverType.ASYNC_TASK_STATUS, run_async_task_observer)
    registry.register(ObserverType.AZURE_QUEUE_PEEK, run_azure_queue_observer)
    registry.register(ObserverType.AZURE_BLOB_OBJECT, run_azure_blob_observer)
    return registry
