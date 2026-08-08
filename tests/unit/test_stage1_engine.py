from __future__ import annotations

from pathlib import Path

from jiejian.domain.models import CaseVerdict, RunVerdict
from jiejian.domain.stage1 import (
    ContractRule,
    MutationCase,
    MutationKind,
    Observation,
    RuleKind,
)
from jiejian.engine import (
    aggregate_verdict,
    build_evidence,
    build_mutation_plan,
    evaluate_case,
)
from jiejian.inputs import load_project_bundle


SAMPLE_PROJECT = (
    Path(__file__).resolve().parents[2]
    / "samples"
    / "projects"
    / "ownership-safe"
    / "project.yaml"
)


def test_mutation_plan_is_deterministic_for_fixed_seed() -> None:
    bundle = load_project_bundle(SAMPLE_PROJECT)
    first = build_mutation_plan(bundle.project, bundle.flow, bundle.contract, seed=17)
    second = build_mutation_plan(bundle.project, bundle.flow, bundle.contract, seed=17)
    assert [case.case_id for case in first.cases] == [case.case_id for case in second.cases]
    assert [case.fingerprint for case in first.cases] == [
        case.fingerprint for case in second.cases
    ]
    assert {case.mutation for case in first.cases} == {
        MutationKind.IDENTITY_SWAP,
        MutationKind.RESOURCE_SWAP,
        MutationKind.PRIVILEGED_FIELD,
    }


def test_oracle_uses_observations_instead_of_http_rejection() -> None:
    side_effect_case = _case(MutationKind.IDENTITY_SWAP)
    side_effect_rule = _rule(RuleKind.UNAUTHORIZED_SIDE_EFFECT)
    observations = (
        Observation(observer="http", phase="mutation", status_code=403),
        Observation(observer="owner_api", phase="before", status_code=200, data={"value": "old"}),
        Observation(observer="owner_api", phase="after", status_code=200, data={"value": "new"}),
    )
    verdict, reasons = evaluate_case(side_effect_case, side_effect_rule, observations)
    assert verdict is CaseVerdict.VULNERABLE
    assert reasons == ("UNAUTHORIZED_SIDE_EFFECT",)

    missing_verdict, missing_reasons = evaluate_case(
        side_effect_case,
        side_effect_rule,
        observations[:1],
    )
    assert missing_verdict is CaseVerdict.INCONCLUSIVE
    assert missing_reasons == ("REQUIRED_OBSERVER_MISSING",)


def test_oracle_detects_foreign_read_and_privileged_field() -> None:
    foreign_verdict, foreign_reasons = evaluate_case(
        _case(MutationKind.IDENTITY_SWAP),
        _rule(RuleKind.FOREIGN_READ),
        (
            Observation(
                observer="http",
                phase="mutation",
                status_code=200,
                data={"id": "foreign"},
            ),
        ),
    )
    assert foreign_verdict is CaseVerdict.VULNERABLE
    assert foreign_reasons == ("FOREIGN_RESOURCE_OBSERVED",)

    privileged_verdict, privileged_reasons = evaluate_case(
        _case(MutationKind.PRIVILEGED_FIELD),
        _rule(RuleKind.PRIVILEGED_FIELD),
        (
            Observation(observer="http", phase="mutation", status_code=403),
            Observation(
                observer="owner_api",
                phase="before",
                status_code=200,
                data={"owner_id": "owner", "role": "user"},
            ),
            Observation(
                observer="owner_api",
                phase="after",
                status_code=200,
                data={"owner_id": "attacker", "role": "admin"},
            ),
        ),
    )
    assert privileged_verdict is CaseVerdict.VULNERABLE
    assert privileged_reasons == ("PRIVILEGED_FIELD_ACCEPTED",)


def test_evidence_hash_and_redaction_are_stable() -> None:
    secret = "do-not-persist-this-secret"
    case = _case(MutationKind.IDENTITY_SWAP).model_copy(
        update={"json_body": {"password": secret}}
    )
    observations = (
        Observation(
            observer="http",
            phase="mutation",
            status_code=403,
            data={"Authorization": f"Bearer {secret}"},
        ),
    )
    first = build_evidence(
        case,
        run_id="run_test",
        verdict=CaseVerdict.SAFE,
        reason_codes=(),
        observations=observations,
    )
    second = build_evidence(
        case,
        run_id="run_test",
        verdict=CaseVerdict.SAFE,
        reason_codes=(),
        observations=observations,
    )
    assert first.evidence_hash == second.evidence_hash
    assert secret not in first.model_dump_json()


def test_aggregate_verdict_priorities() -> None:
    safe = build_evidence(_case(MutationKind.IDENTITY_SWAP), run_id="run_test", verdict=CaseVerdict.SAFE, reason_codes=(), observations=())
    vulnerable = build_evidence(
        _case(MutationKind.RESOURCE_SWAP),
        run_id="run_test",
        verdict=CaseVerdict.VULNERABLE,
        reason_codes=("UNAUTHORIZED_SIDE_EFFECT",),
        observations=(),
    )
    inconclusive = build_evidence(
        _case(MutationKind.PRIVILEGED_FIELD),
        run_id="run_test",
        verdict=CaseVerdict.INCONCLUSIVE,
        reason_codes=("REQUIRED_OBSERVER_MISSING",),
        observations=(),
    )
    assert aggregate_verdict((safe,)) is RunVerdict.PASS
    assert aggregate_verdict((safe, inconclusive)) is RunVerdict.INCONCLUSIVE
    assert aggregate_verdict((inconclusive, vulnerable)) is RunVerdict.BLOCK


def _case(mutation: MutationKind) -> MutationCase:
    return MutationCase(
        case_id=f"case-{mutation.value}",
        fingerprint=f"fingerprint-{mutation.value}",
        step_id="step",
        rule_id="rule",
        mutation=mutation,
        method="PATCH",
        path="/resources/owner-resource",
        identity_id="attacker",
        resource_id="owner-resource",
        owner_identity_id="owner",
        json_body={"value": "new"},
    )


def _rule(kind: RuleKind) -> ContractRule:
    return ContractRule(
        id="rule",
        kind=kind,
        required_observers=("http", "owner_api"),
    )
