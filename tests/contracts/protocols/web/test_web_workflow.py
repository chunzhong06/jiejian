# 验证 Web workflow 协议 Schema 与基线绑定边界。

from __future__ import annotations
import pytest
from pydantic import ValidationError
from product.protocols.web.request import HttpRequestTemplate
from product.protocols.web.workflow import HttpWorkflowBinding, HttpWorkflowStep, WorkflowStepPurpose


def test_not_required_reset_only_accepts_read_only_workflow() -> None:
    target = HttpWorkflowStep(
        id="read-project",
        purpose=WorkflowStepPurpose.TARGET,
        identity_id="CASE_SUBJECT",
        request_template=HttpRequestTemplate(method="GET", path="/projects/example"),
    )

    workflow = HttpWorkflowBinding(
        workflow_id="read-project-workflow",
        source_flow_id="read-project-flow",
        action_id="read-project-action",
        steps=(target,),
        target_step_id=target.id,
        reset_strategy={"kind": "NOT_REQUIRED"},
    )

    assert workflow.reset_strategy.kind.value == "NOT_REQUIRED"
    with pytest.raises(ValidationError, match="only supports read-only"):
        HttpWorkflowBinding(
            workflow_id="write-project-workflow",
            source_flow_id="write-project-flow",
            action_id="write-project-action",
            steps=(
                target.model_copy(
                    update={
                        "request_template": HttpRequestTemplate(
                            method="POST",
                            path="/projects/example",
                        )
                    }
                ),
            ),
            target_step_id=target.id,
            reset_strategy={"kind": "NOT_REQUIRED"},
        )
