# 验证内部生成的 Web 执行输入与录制绑定可通过当前协议类型。

from __future__ import annotations

from pathlib import Path

from product.backend.core.verification.permissions import PermissionContract
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.protocols import (
    ExecutionBudget,
    RunnerInput,
)
from product.protocols.web.profile import (
    canonical_web_execution_profile_json_bytes,
    parse_web_execution_profile,
)
from tests.fixtures.runner import write_web_test_profile


ACTION_CANDIDATE_ID = "action_0123456789abcdef0123456789abcdef"


def test_programmatic_profile_compiles_through_current_execution_types(tmp_path: Path) -> None:
    path, contract_path = write_web_test_profile(
        tmp_path, include_comparison_subject=True
    )
    profile = parse_web_execution_profile(path.read_bytes())
    contract = PermissionContract.model_validate_json(contract_path.read_bytes(), strict=True)
    plan = ExecutionWorkflow._compile_plan(profile, contract)
    assert not plan.gaps
    snapshot = profile.build_snapshot(contract, plan)
    runner_input = RunnerInput(
        run_id="run_" + "a" * 32,
        job_id="job_" + "b" * 32,
        attempt=1,
        lease_owner="programmatic-test",
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
    assert len(plan.cases) == 2
    assert canonical_web_execution_profile_json_bytes(profile).rstrip() == path.read_bytes().rstrip()
