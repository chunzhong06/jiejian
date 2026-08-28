# 验证观察器基础设施中的观察事实投影。

from __future__ import annotations

from pathlib import Path

import pytest

from product.backend.core.lifecycle import CaseVerdict
from product.backend.core.verification.facts import (
    ObservedEffect,
    SecurityEffectFact,
    TemporalClosure,
)
from product.backend.core.verification.permissions import SecurityEffectKind
from product.backend.infra.observers.coordinator import ObserverCoordinator
from product.backend.infra.observers.registry import ObserverRegistry
from product.backend.infra.runtime.runner.executor import (
    _apply_required_observer_guard,
)
from product.protocols import (
    CausalityStatus,
    Correlation,
    ObservationCompleteness,
    ObservationEnvelope,
    ObservationPhase,
    ObservationProvenance,
    ObservationWindow,
    ObserverOutcome,
    ObserverOutcomeStatus,
    ObserverType,
    ProvenanceType,
    build_normalized_state,
)
from tests.fixtures.runner import runner_input


_PROVENANCE_TYPES = {
    ObserverType.OWNER_API: ProvenanceType.OWNER_API,
    ObserverType.READ_ONLY_SQLITE: ProvenanceType.SQLITE_QUERY,
    ObserverType.STRUCTURED_AUDIT_LOG: ProvenanceType.AUDIT_LOG_WINDOW,
    ObserverType.ASYNC_TASK_STATUS: ProvenanceType.ASYNC_TASK_API,
    ObserverType.AZURE_QUEUE_PEEK: ProvenanceType.AZURE_QUEUE_PEEK,
    ObserverType.AZURE_BLOB_OBJECT: ProvenanceType.AZURE_BLOB_OBJECT,
}


def _case_and_binding(
    observer_type: ObserverType,
    phases: tuple[ObservationPhase, ...],
):
    document = runner_input()
    case = document.project_snapshot.plan.cases[0]
    binding = document.project_snapshot.observer_bindings[0].model_copy(
        update={"observer_type": observer_type, "phases": phases}
    )
    return case, binding


def _coordinator(binding) -> ObserverCoordinator:
    return ObserverCoordinator(
        registry=ObserverRegistry(),
        specs={},
        bindings={binding.requirement_id: binding},
        environ={},
        attempt_dir=Path("."),
        clock=lambda: 1,
        cancellation_requested=lambda: False,
    )


def _envelope(
    case,
    observer_type: ObserverType,
    phase: ObservationPhase,
    payload: dict[str, object],
) -> ObservationEnvelope:
    state = build_normalized_state(payload)
    provenance_type = _PROVENANCE_TYPES[observer_type]
    return ObservationEnvelope(
        observer_id="owner_observer",
        observer_type=observer_type,
        phase=phase,
        target_id="fact-target",
        window=ObservationWindow(
            phase=phase,
            started_at_us=1,
            finished_at_us=2,
            timeout_us=10,
        ),
        correlation=Correlation(
            case_id=case.case_id,
            resource_id=case.resource_ids[0],
            request_marker=case.case_id,
        ),
        causality=CausalityStatus.CORRELATED,
        completeness=ObservationCompleteness.COMPLETE,
        state=state,
        provenance=ObservationProvenance(
            provenance_type=provenance_type,
            adapter_version="fact-test",
            target_id="fact-target",
            query_template_id=(
                "fact-query"
                if provenance_type is ProvenanceType.SQLITE_QUERY
                else None
            ),
            source_sha256=state.canonical_sha256,
        ),
    )


def _project(
    observer_type: ObserverType,
    phases: tuple[ObservationPhase, ...],
    payloads: tuple[tuple[ObservationPhase, dict[str, object]], ...],
):
    case, binding = _case_and_binding(observer_type, phases)
    envelopes = tuple(
        _envelope(case, observer_type, phase, payload)
        for phase, payload in payloads
    )
    fact = _coordinator(binding).project_facts(case, envelopes)[0]
    return fact


@pytest.mark.parametrize(
    "observer_type",
    (
        ObserverType.OWNER_API,
        ObserverType.READ_ONLY_SQLITE,
        ObserverType.AZURE_BLOB_OBJECT,
    ),
)
def test_state_observers_compare_closed_before_and_after(
    observer_type: ObserverType,
) -> None:
    phases = (ObservationPhase.BEFORE, ObservationPhase.AFTER)
    changed = _project(
        observer_type,
        phases,
        (
            (ObservationPhase.BEFORE, {"value": "old"}),
            (ObservationPhase.AFTER, {"value": "new"}),
        ),
    )
    unchanged = _project(
        observer_type,
        phases,
        (
            (ObservationPhase.BEFORE, {"value": "same"}),
            (ObservationPhase.AFTER, {"value": "same"}),
        ),
    )

    assert changed.effect is ObservedEffect.CONFIRMED
    assert unchanged.effect is ObservedEffect.ABSENT
    assert changed.temporal_closure is unchanged.temporal_closure is TemporalClosure.CLOSED


def test_open_or_missing_state_observation_cannot_prove_absence() -> None:
    phases = (
        ObservationPhase.BEFORE,
        ObservationPhase.AFTER,
        ObservationPhase.EVENTUAL,
    )
    open_fact = _project(
        ObserverType.OWNER_API,
        phases,
        (
            (ObservationPhase.BEFORE, {"value": "same"}),
            (ObservationPhase.EVENTUAL, {"value": "same"}),
        ),
    )
    case, binding = _case_and_binding(ObserverType.OWNER_API, phases)
    missing_fact = _coordinator(binding).project_facts(case, ())[0]

    assert open_fact.effect is ObservedEffect.UNKNOWN
    assert open_fact.temporal_closure is TemporalClosure.OPEN
    assert missing_fact.effect is ObservedEffect.UNKNOWN
    assert missing_fact.reason_codes == ("REQUIRED_OBSERVER_INCOMPLETE",)


def test_audit_log_uses_side_effect_semantics_instead_of_state_hash() -> None:
    phases = (ObservationPhase.BEFORE, ObservationPhase.AFTER)
    confirmed = _project(
        ObserverType.STRUCTURED_AUDIT_LOG,
        phases,
        (
            (ObservationPhase.BEFORE, {"records": []}),
            (
                ObservationPhase.AFTER,
                {"records": [{"event_type": "SIDE_EFFECT", "effect": "APPLIED"}]},
            ),
        ),
    )
    absent = _project(
        ObserverType.STRUCTURED_AUDIT_LOG,
        phases,
        (
            (ObservationPhase.BEFORE, {"records": [{"event_type": "REQUEST"}]}),
            (ObservationPhase.AFTER, {"records": [{"event_type": "REQUEST"}]}),
        ),
    )

    assert confirmed.effect is ObservedEffect.CONFIRMED
    assert absent.effect is ObservedEffect.ABSENT


def test_async_task_requires_interpretable_closed_terminal_state() -> None:
    phases = (ObservationPhase.AFTER, ObservationPhase.EVENTUAL)
    confirmed = _project(
        ObserverType.ASYNC_TASK_STATUS,
        phases,
        (
            (ObservationPhase.AFTER, {"task_state": "RUNNING"}),
            (
                ObservationPhase.EVENTUAL,
                {"task_state": "SUCCESS", "final_result": {"effect": "APPLIED"}},
            ),
        ),
    )
    absent = _project(
        ObserverType.ASYNC_TASK_STATUS,
        phases,
        (
            (ObservationPhase.AFTER, {"task_state": "RUNNING"}),
            (ObservationPhase.EVENTUAL, {"task_state": "NOT_CREATED"}),
        ),
    )
    unknown = _project(
        ObserverType.ASYNC_TASK_STATUS,
        phases,
        (
            (ObservationPhase.AFTER, {"task_state": "RUNNING"}),
            (ObservationPhase.EVENTUAL, {"task_state": "FAILED"}),
        ),
    )

    assert confirmed.effect is ObservedEffect.CONFIRMED
    assert absent.effect is ObservedEffect.ABSENT
    assert unknown.effect is ObservedEffect.UNKNOWN
    assert unknown.reason_codes == ("OBSERVATION_UNINTERPRETED",)


def test_eventual_only_async_observation_closes_when_terminal_envelope_is_complete() -> None:
    phases = (ObservationPhase.EVENTUAL,)
    case, binding = _case_and_binding(ObserverType.ASYNC_TASK_STATUS, phases)
    envelope = _envelope(
        case,
        ObserverType.ASYNC_TASK_STATUS,
        ObservationPhase.EVENTUAL,
        {"task_state": "SUCCESS", "final_result": {"effect": "APPLIED"}},
    )

    fact = _coordinator(binding).project_facts(case, (envelope,))[0]

    assert fact.effect is ObservedEffect.CONFIRMED
    assert fact.temporal_closure is TemporalClosure.CLOSED


def test_eventual_only_async_missing_envelope_stays_unknown() -> None:
    case, binding = _case_and_binding(
        ObserverType.ASYNC_TASK_STATUS,
        (ObservationPhase.EVENTUAL,),
    )

    fact = _coordinator(binding).project_facts(case, ())[0]

    assert fact.effect is ObservedEffect.UNKNOWN
    assert fact.temporal_closure is TemporalClosure.UNKNOWN
    assert fact.reason_codes == ("REQUIRED_OBSERVER_INCOMPLETE",)


def test_eventual_only_queue_observation_closes_when_window_is_complete() -> None:
    phases = (ObservationPhase.EVENTUAL,)
    case, binding = _case_and_binding(ObserverType.AZURE_QUEUE_PEEK, phases)
    envelope = _envelope(
        case,
        ObserverType.AZURE_QUEUE_PEEK,
        ObservationPhase.EVENTUAL,
        {"window_complete": True, "matched_count": 0, "messages": []},
    )

    fact = _coordinator(binding).project_facts(case, (envelope,))[0]

    assert fact.effect is ObservedEffect.ABSENT
    assert fact.temporal_closure is TemporalClosure.CLOSED


def test_eventual_only_queue_incomplete_window_stays_unknown_and_open() -> None:
    case, binding = _case_and_binding(
        ObserverType.AZURE_QUEUE_PEEK,
        (ObservationPhase.EVENTUAL,),
    )
    envelope = _envelope(
        case,
        ObserverType.AZURE_QUEUE_PEEK,
        ObservationPhase.EVENTUAL,
        {"window_complete": False, "matched_count": 0, "messages": []},
    )

    fact = _coordinator(binding).project_facts(case, (envelope,))[0]

    assert fact.effect is ObservedEffect.UNKNOWN
    assert fact.temporal_closure is TemporalClosure.OPEN
    assert fact.reason_codes == ("OBSERVATION_WINDOW_INCOMPLETE",)


def test_queue_requires_a_closed_and_explicit_window_for_absence() -> None:
    phases = (ObservationPhase.AFTER, ObservationPhase.EVENTUAL)
    absent = _project(
        ObserverType.AZURE_QUEUE_PEEK,
        phases,
        (
            (ObservationPhase.AFTER, {"window_complete": True, "matched_count": 0, "messages": []}),
            (ObservationPhase.EVENTUAL, {"window_complete": True, "matched_count": 0, "messages": []}),
        ),
    )
    confirmed = _project(
        ObserverType.AZURE_QUEUE_PEEK,
        phases,
        (
            (ObservationPhase.AFTER, {"window_complete": True, "matched_count": 0, "messages": []}),
            (ObservationPhase.EVENTUAL, {"window_complete": True, "matched_count": 1, "messages": [{"event_id": "one"}]}),
        ),
    )
    open_window = _project(
        ObserverType.AZURE_QUEUE_PEEK,
        phases,
        (
            (ObservationPhase.EVENTUAL, {"window_complete": True, "matched_count": 0, "messages": []}),
        ),
    )

    assert absent.effect is ObservedEffect.ABSENT
    assert confirmed.effect is ObservedEffect.CONFIRMED
    assert open_window.effect is ObservedEffect.UNKNOWN
    assert open_window.temporal_closure is TemporalClosure.OPEN
    assert open_window.reason_codes == ("OBSERVATION_WINDOW_INCOMPLETE",)


def _security_effect(closure: TemporalClosure) -> SecurityEffectFact:
    return SecurityEffectFact(
        effect_id="document-mutated",
        kind=SecurityEffectKind.STATE_MUTATION,
        resource_id="document",
        state=ObservedEffect.CONFIRMED,
        complete=True,
        reliable=True,
        correlated=True,
        temporal_closure=closure,
        baseline_integrity=True,
        source_requirement_ids=("resource_state",),
        reason_codes=()
        if closure is TemporalClosure.CLOSED
        else ("TEMPORAL_WINDOW_OPEN",),
    )


def test_missing_required_outcome_cannot_bypass_conservative_guard() -> None:
    case, binding = _case_and_binding(
        ObserverType.OWNER_API,
        (ObservationPhase.BASELINE, ObservationPhase.BEFORE, ObservationPhase.AFTER),
    )
    coordinator = _coordinator(binding)
    outcomes = coordinator.complete_required_outcomes(case, ())

    verdict, reasons = _apply_required_observer_guard(
        case,
        {binding.requirement_id: binding},
        outcomes,
        (_security_effect(TemporalClosure.OPEN),),
        CaseVerdict.SAFE,
        (),
    )

    assert outcomes[0].required is True
    assert outcomes[0].status is ObserverOutcomeStatus.INCONCLUSIVE
    assert verdict is CaseVerdict.INCONCLUSIVE
    assert reasons == ("REQUIRED_OBSERVER_INCOMPLETE",)


def test_unavailable_after_or_eventual_outcome_downgrades_safe() -> None:
    case, binding = _case_and_binding(
        ObserverType.OWNER_API,
        (ObservationPhase.BASELINE, ObservationPhase.BEFORE, ObservationPhase.AFTER),
    )
    unavailable = (
        ObserverOutcome(
            observer_id=binding.observer_id,
            required=True,
            status=ObserverOutcomeStatus.INCONCLUSIVE,
            reason_codes=("REQUIRED_OBSERVER_INCOMPLETE",),
        ),
    )

    verdict, reasons = _apply_required_observer_guard(
        case,
        {binding.requirement_id: binding},
        unavailable,
        (_security_effect(TemporalClosure.CLOSED),),
        CaseVerdict.SAFE,
        (),
    )

    assert verdict is CaseVerdict.INCONCLUSIVE
    assert reasons == ("REQUIRED_OBSERVER_INCOMPLETE",)


def test_closed_authoritative_effect_preserves_vulnerable_verdict() -> None:
    case, binding = _case_and_binding(
        ObserverType.OWNER_API,
        (ObservationPhase.BASELINE, ObservationPhase.BEFORE, ObservationPhase.AFTER),
    )
    unavailable = (
        ObserverOutcome(
            observer_id=binding.observer_id,
            required=True,
            status=ObserverOutcomeStatus.INCONCLUSIVE,
            reason_codes=("REQUIRED_OBSERVER_INCOMPLETE",),
        ),
    )

    verdict, reasons = _apply_required_observer_guard(
        case,
        {binding.requirement_id: binding},
        unavailable,
        (_security_effect(TemporalClosure.CLOSED),),
        CaseVerdict.VULNERABLE,
        ("UNAUTHORIZED_EFFECT_CONFIRMED",),
    )

    assert verdict is CaseVerdict.VULNERABLE
    assert reasons == ("UNAUTHORIZED_EFFECT_CONFIRMED",)
