from __future__ import annotations

from product.backend.core.verification.permissions import permission_model_sha256
from product.backend.workflows.contracts.setup_minimizer import minimize_failure_setup
from product.protocols.web.workflow import CASE_SUBJECT_IDENTITY
from product.protocols import (
    HttpOutcomeClassifier,
    HttpRequestTemplate,
    HttpWorkflowBinding,
    HttpWorkflowStep,
    WorkflowStepPurpose,
)
from tests.fixtures.runner import execution_snapshot


def test_failure_minimizer_removes_only_unused_setup_and_preserves_security_problem() -> None:
    snapshot = execution_snapshot()
    original = snapshot.workflow_bindings[0]
    setup = HttpWorkflowStep(
        id="optional-setup",
        purpose=WorkflowStepPurpose.SETUP,
        identity_id=CASE_SUBJECT_IDENTITY,
        request_template=HttpRequestTemplate(method="GET", path="/optional-setup"),
        classifier=HttpOutcomeClassifier(),
    )
    workflow = HttpWorkflowBinding.model_validate(
        {
            **original.model_dump(mode="python"),
            "steps": (setup, *original.steps),
            "workflow_fingerprint": None,
        }
    )
    target_before = next(step for step in workflow.steps if step.id == workflow.target_step_id)
    result = minimize_failure_setup(
        workflow,
        snapshot.plan.cases[0],
        security_effect_fingerprint=permission_model_sha256(snapshot.contract.effects),
        reproduces=lambda candidate: any(
            step.id == candidate.target_step_id and step.request_template == target_before.request_template
            for step in candidate.steps
        ),
    )
    assert result.removed_setup_step_ids == ("optional-setup",)
    assert all(step.purpose is not WorkflowStepPurpose.SETUP for step in result.minimized_workflow.steps)
    assert result.minimized_workflow.target_step_id == workflow.target_step_id
    assert result.minimized_workflow.baseline_projections == workflow.baseline_projections
