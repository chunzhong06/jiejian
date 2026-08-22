from __future__ import annotations

from product.backend.core.verification.facts import (
    DisclosureProof,
    ObservationFact,
    ObservedEffect,
    TemporalClosure,
    aggregate_security_effect,
)
from product.backend.core.verification.permissions import (
    SecurityEffectDefinition,
    SecurityEffectKind,
)


def _observation(
    requirement_id: str,
    state: ObservedEffect,
    *,
    closed: bool = True,
) -> ObservationFact:
    complete = state is not ObservedEffect.UNKNOWN
    return ObservationFact(
        requirement_id=requirement_id,
        resource_id="document",
        effect=state,
        complete=complete,
        reliable=complete,
        correlated=complete,
        temporal_closure=TemporalClosure.CLOSED if closed else TemporalClosure.OPEN,
        reason_codes=() if complete and closed else ("OBSERVATION_INCOMPLETE",),
    )


def test_authoritative_confirmation_blocks_despite_unknown_auxiliary_channel() -> None:
    effect = SecurityEffectDefinition(
        effect_id="document-mutated",
        kind=SecurityEffectKind.STATE_MUTATION,
        resource_type="document",
    )
    fact = aggregate_security_effect(
        effect,
        resource_id="document",
        required_requirement_ids=("resource_state",),
        corroborating_requirement_ids=("sql_trace",),
        observations=(
            _observation("resource_state", ObservedEffect.CONFIRMED),
            _observation("sql_trace", ObservedEffect.UNKNOWN, closed=False),
        ),
        baseline_integrity=True,
    )
    assert fact.state is ObservedEffect.CONFIRMED
    assert fact.source_requirement_ids == ("resource_state",)


def test_absence_requires_every_authoritative_channel_and_closed_baseline() -> None:
    effect = SecurityEffectDefinition(
        effect_id="document-mutated",
        kind=SecurityEffectKind.STATE_MUTATION,
        resource_type="document",
    )
    absent = aggregate_security_effect(
        effect,
        resource_id="document",
        required_requirement_ids=("resource_state",),
        corroborating_requirement_ids=(),
        observations=(_observation("resource_state", ObservedEffect.ABSENT),),
        baseline_integrity=True,
    )
    open_fact = aggregate_security_effect(
        effect,
        resource_id="document",
        required_requirement_ids=("resource_state",),
        corroborating_requirement_ids=(),
        observations=(_observation("resource_state", ObservedEffect.ABSENT, closed=False),),
        baseline_integrity=True,
    )
    assert absent.state is ObservedEffect.ABSENT
    assert open_fact.state is ObservedEffect.UNKNOWN


def test_disclosure_fact_persists_only_digest_proof() -> None:
    effect = SecurityEffectDefinition(
        effect_id="document-disclosed",
        kind=SecurityEffectKind.DATA_DISCLOSURE,
        resource_type="document",
        protected_fields=("content",),
    )
    proof = DisclosureProof(
        projection_version="v1",
        projection_complete=True,
        owner_digest="a" * 64,
        response_digest="a" * 64,
        matched=True,
        correlation_digest="b" * 64,
    )
    fact = aggregate_security_effect(
        effect,
        resource_id="document",
        required_requirement_ids=("http_response",),
        corroborating_requirement_ids=(),
        observations=(_observation("http_response", ObservedEffect.CONFIRMED),),
        baseline_integrity=True,
        disclosure_proof=proof,
    )
    serialized = fact.model_dump_json()
    assert fact.state is ObservedEffect.CONFIRMED
    assert "owner_digest" in serialized
    assert "content" not in serialized
    assert "canary" not in serialized
