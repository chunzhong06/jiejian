from __future__ import annotations

import json
from pathlib import Path

from product.backend.core.verification.differential import DifferentialExperimentPlan
from product.backend.core.verification.permission_coverage import build_permission_coverage_plan
from product.backend.core.verification.permissions import PermissionContract
from product.protocols.execution_profile import ExecutionProfile


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def test_http_samples_build_stable_single_variation_permission_twins() -> None:
    fingerprints: set[str] = set()
    for name in ("fixed", "vulnerable", "inconclusive"):
        sample = PROJECT_ROOT / "samples" / "http" / name
        contract = PermissionContract.model_validate_json(
            (sample / "contract.json").read_text(encoding="utf-8")
        )
        profile = ExecutionProfile.model_validate_json(
            (sample / "profile.json").read_text(encoding="utf-8")
        )
        coverage = build_permission_coverage_plan(
            contract,
            engine_version="coverage-v2",
            seed=profile.seed,
            case_budget=profile.case_budget,
            max_relation_depth=profile.max_relation_depth,
        )
        snapshot = profile.build_snapshot(contract, coverage)
        assert len(snapshot.differential_plan.twins) == 2
        assert snapshot.differential_plan.gaps == ()
        assert all(twin.mutation.changed_fields for twin in snapshot.differential_plan.twins)
        assert all(
            twin.allow_case.action_id == twin.deny_case.action_id
            and twin.allow_case.resource_ids == twin.deny_case.resource_ids
            for twin in snapshot.differential_plan.twins
        )
        fingerprints.add(snapshot.differential_fingerprint)
    assert len(fingerprints) == 1


def test_checked_in_differential_plan_schema_has_no_drift() -> None:
    checked_in = json.loads(
        (
            PROJECT_ROOT
            / "product"
            / "protocols"
            / "schemas"
            / "contracts"
            / "differential-experiment-plan.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert checked_in == DifferentialExperimentPlan.model_json_schema()
