from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from product.backend.core.errors import JiejianError
from product.backend.core.verification.permissions import PermissionContract
from product.backend.workflows.recording.review import compile_flow_bindings
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.protocols import ExecutionBudget, RunnerInput
from product.protocols.execution_profile import canonical_execution_profile_json_bytes, parse_execution_profile
from product.protocols.recording_flow import Flow, FlowStep


ROOT = Path(__file__).resolve().parents[2]
VARIANTS = ("fixed", "vulnerable", "inconclusive")
def _sample_paths() -> list[Path]:
    return [ROOT / "samples" / "http" / variant / "profile.json" for variant in VARIANTS]


def test_all_official_sample_profiles_compile_through_current_execution_types() -> None:
    for path in _sample_paths():
        profile = parse_execution_profile(path.read_bytes())
        contract = PermissionContract.model_validate_json(path.with_name("contract.json").read_bytes(), strict=True)
        plan = ExecutionWorkflow._compile_plan(profile, contract)
        assert not plan.gaps
        snapshot = profile.build_snapshot(contract, plan)
        runner_input = RunnerInput(
            run_id="run_" + "a" * 32,
            job_id="job_" + "b" * 32,
            attempt=1,
            lease_owner="sample-test",
            fencing_token=1,
            created_at_us=1,
            budget=ExecutionBudget(
                max_requests=profile.target.scope.max_requests,
                request_timeout_us=int(profile.target.scope.timeout_seconds * 1_000_000),
                max_duration_us=profile.max_duration_us,
                max_response_bytes=profile.target.scope.max_response_bytes,
                max_cases=profile.case_budget,
                max_parallel_cases=1,
            ),
            project_snapshot=snapshot,
        )
        assert snapshot.project_id == profile.project_id
        assert snapshot.plan.cases
        assert snapshot.plan.cases[0].required_observations
        assert runner_input.project_snapshot is snapshot
        scenario = json.loads(path.with_name("scenario.json").read_text(encoding="utf-8"))
        expected_count = scenario["formal_profile"].get("retained_case_count")
        if expected_count is None:
            expected_count = scenario["formal_profile"]["required_case_count"]
        assert len(plan.cases) == expected_count
        assert canonical_execution_profile_json_bytes(profile).rstrip() == path.read_bytes().rstrip()
        truth = json.loads(path.with_name("truth.json").read_text(encoding="utf-8"))
        assert truth["formal_profile"]["run_verdict"] in {"PASS", "BLOCK", "INCONCLUSIVE"}


def test_recording_flow_compiles_to_authorization_profile_bindings() -> None:
    path = ROOT / "samples" / "http" / "fixed" / "profile.json"
    profile = parse_execution_profile(path.read_bytes())
    contract = PermissionContract.model_validate_json(path.with_name("contract.json").read_bytes(), strict=True)
    plan = ExecutionWorkflow._compile_plan(profile, contract)
    step = FlowStep(
        id="modify-step",
        method="PATCH",
        path="/resources/{resource_id}",
        identity_id="owner",
        resource_id="owner-resource",
        alternate_identity_id="attacker",
        alternate_resource_id="owner-resource",
        json_body={"value": "recorded-value"},
        action_ids=("modify",),
    )
    valid_flow = Flow(id="recorded-flow", reset_path="/reset", steps=(step,))
    target_override, action_bindings_override = compile_flow_bindings(valid_flow, profile)
    snapshot = profile.build_snapshot(contract, plan, target_override=target_override, action_bindings_override=action_bindings_override)
    assert snapshot.target.reset_path == "/reset"
    invalid_flow = Flow(id="invalid-flow", reset_path="/reset", steps=(step.model_copy(update={"action_ids": ()}),))
    with pytest.raises((JiejianError, ValidationError, ValueError)):
        compile_flow_bindings(invalid_flow, profile)
    duplicate_flow = Flow(id="duplicate-flow", reset_path="/reset", steps=(step, step.model_copy(update={"id": "duplicate-step"})))
    with pytest.raises(JiejianError):
        compile_flow_bindings(duplicate_flow, profile)
