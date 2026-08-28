# 验证权限契约能够稳定生成差分执行计划。

from __future__ import annotations

import json
from pathlib import Path

from product.backend.core.verification.differential import DifferentialExperimentPlan
from product.backend.core.verification.permissions.coverage import build_permission_coverage_plan
from product.backend.core.verification.permissions import PermissionContract
from product.protocols.web.profile import WebExecutionProfile
from tests.fixtures.runner import write_web_test_profile


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def test_programmatic_differential_plan_is_stable(tmp_path: Path) -> None:
    profile_path, contract_path = write_web_test_profile(
        tmp_path, include_comparison_subject=True
    )
    contract = PermissionContract.model_validate_json(contract_path.read_text(encoding="utf-8"))
    profile = WebExecutionProfile.model_validate_json(profile_path.read_text(encoding="utf-8"))
    coverage = build_permission_coverage_plan(
        contract,
        engine_version="coverage-v2",
        seed=profile.seed,
        case_budget=profile.case_budget,
        max_relation_depth=profile.max_relation_depth,
    )
    snapshot = profile.build_snapshot(contract, coverage)
    assert len(snapshot.differential_plan.twins) == 1
    assert snapshot.differential_plan.gaps == ()
    assert all(twin.mutation.changed_fields for twin in snapshot.differential_plan.twins)
    assert all(
        twin.allow_case.action_id == twin.deny_case.action_id
        and twin.allow_case.resource_ids == twin.deny_case.resource_ids
        for twin in snapshot.differential_plan.twins
    )


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
