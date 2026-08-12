from __future__ import annotations

import pytest
from pydantic import ValidationError

from jiejian.domain.lifecycle import (
    CaseLifecycle,
    CaseVerdict,
    ContractStatus,
    DomainModel,
    JobState,
    ProjectStatus,
    RunLifecycle,
    RunVerdict,
)


@pytest.mark.parametrize(
    ("enum_type", "expected"),
    [
        (ProjectStatus, {"DRAFT", "READY", "ARCHIVED"}),
        (ContractStatus, {"DRAFT", "REVIEW", "ACTIVE", "SUPERSEDED", "REJECTED"}),
        (
            RunLifecycle,
            {
                "QUEUED",
                "PREFLIGHT",
                "PLANNING",
                "EXECUTING",
                "VERIFYING",
                "REPORTING",
                "COMPLETED",
                "FAILED",
                "CANCELLED",
                "SAFETY_STOPPED",
            },
        ),
        (RunVerdict, {"PASS", "BLOCK", "INCONCLUSIVE"}),
        (CaseLifecycle, {"PLANNED", "SNAPSHOTTED", "EXECUTED", "OBSERVED", "CLEANED", "DONE", "ERROR"}),
        (CaseVerdict, {"SAFE", "VULNERABLE", "INCONCLUSIVE", "SKIPPED", "ERROR"}),
        (JobState, {"PENDING", "RUNNING", "RETRY_WAIT", "SUCCEEDED", "FAILED", "CANCELLED"}),
    ],
)
def test_shared_lifecycle_enum_values_are_stable(enum_type, expected) -> None:
    assert {state.value for state in enum_type} == expected


def test_domain_model_public_schema_baseline_is_stable() -> None:
    model = DomainModel()
    assert model.schema_version == "1"
    assert DomainModel.model_config["extra"] == "forbid"
    assert DomainModel.model_config["frozen"] is True

    with pytest.raises(ValidationError):
        DomainModel(unexpected=True)
    with pytest.raises(ValidationError):
        model.schema_version = "2"
