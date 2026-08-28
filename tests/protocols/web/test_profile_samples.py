# 验证程序化 Web Profile 与录制绑定可通过当前协议类型。

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from product.backend.core.errors import JiejianError
from product.backend.core.verification.permissions import PermissionContract
from product.backend.workflows.recording.flow_compiler import compile_flow_bindings
from product.backend.workflows.runs.execution import ExecutionWorkflow
from product.protocols import (
    ExecutionBudget,
    HttpOutcomeClassifier,
    HttpPredicate,
    HttpPredicateKind,
    HttpRequestTemplate,
    RunnerInput,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
    WorkflowStepPurpose,
)
from product.protocols.recording_flow import Flow, FlowStep
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


def test_recording_flow_reuses_matching_profile_web_binding(tmp_path: Path) -> None:
    path, _ = write_web_test_profile(tmp_path)
    profile = parse_web_execution_profile(path.read_bytes())
    base_binding = profile.workflow_bindings[0]
    profile = profile.model_copy(
        update={
            "workflow_bindings": (
                base_binding.model_copy(update={"action_id": ACTION_CANDIDATE_ID}),
            )
        }
    )
    step = FlowStep(
        id="modify-step",
        purpose=WorkflowStepPurpose.TARGET,
        request_template=HttpRequestTemplate(
            method="PATCH",
            path="/resources/{resource_id}",
            body={"kind": "JSON", "value": {"value": "recorded-value"}},
            input_slots=(ValueSlot(
                slot_id="resource_id",
                source=ValueSlotSource.CASE_RESOURCE_ID,
                consumer=ValueSlotConsumer.PATH,
                consumer_step_id="modify-step",
            ),),
        ),
        classifier=HttpOutcomeClassifier(
            accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(200,)),)
        ),
    )
    valid_flow = Flow(
        id="recorded-flow",
        action_candidate_id=ACTION_CANDIDATE_ID,
        target_step_id=step.id,
        steps=(step,),
    )
    target_override, workflow_bindings_override = compile_flow_bindings(valid_flow, profile)
    assert target_override == profile.target
    assert target_override.reset_path == "/reset"
    assert len(workflow_bindings_override) == 1
    assert workflow_bindings_override[0].action_id == ACTION_CANDIDATE_ID
    target_step = next(
        item
        for item in workflow_bindings_override[0].steps
        if item.id == workflow_bindings_override[0].target_step_id
    )
    assert target_step.identity_id == "CASE_SUBJECT"
    invalid_flow = valid_flow.model_copy(
        update={"id": "invalid-flow", "action_candidate_id": "action_ffffffffffffffffffffffffffffffff"}
    )
    with pytest.raises((JiejianError, ValidationError, ValueError)):
        compile_flow_bindings(invalid_flow, profile)
    duplicate_profile = profile.model_copy(
        update={
            "workflow_bindings": (
                base_binding.model_copy(update={"action_id": ACTION_CANDIDATE_ID}),
                base_binding.model_copy(update={"action_id": ACTION_CANDIDATE_ID, "workflow_id": "duplicate-workflow"}),
            )
        }
    )
    with pytest.raises(JiejianError):
        compile_flow_bindings(valid_flow, duplicate_profile)
