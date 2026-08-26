# 验证 RunnerResult、cleanup 与稳定错误边界。

from __future__ import annotations
import json
from pathlib import Path
import pytest
from product.backend.core.lifecycle import CaseVerdict, JobState, RunLifecycle, RunVerdict
from product.backend.core.errors import JiejianError
from product.backend.core.verification.facts import ExecutionOutcome, ObservedEffect, TargetType
from product.protocols import (
    CleanupResult,
    CleanupIssue,
    CleanupIssueCode,
    CleanupStatus,
    Evidence,
    PreparedCookieCredential,
    PreparedCookieSessionIdentityBinding,
    RunnerInput,
    RunnerFailurePhase,
    RunnerResult,
    RunnerResultType,
    WebExecutionIdentity,
    build_evidence,
    canonical_runner_json_bytes,
    canonical_runner_sha256,
    parse_runner_result,
    parse_runner_input,
)
from product.protocols.runner.result import _reject_secret_material
from tests.fixtures.runner import evidence, runner_input
pytestmark = pytest.mark.essential

def test_runner_result_root_and_cleanup_completion_contract_are_current() -> None:
    assert RunnerResult.model_fields["schema_version"].default == "1"
    assert CleanupResult(status=CleanupStatus.NOT_REQUIRED).finished_at_us is None
    assert CleanupResult(status=CleanupStatus.SUCCEEDED, finished_at_us=10).finished_at_us == 10
    assert CleanupResult(
        status=CleanupStatus.FAILED,
        finished_at_us=11,
        issues=(CleanupIssue(code=CleanupIssueCode.RUNTIME_CLOSE_FAILED),),
    ).issues[0].code is CleanupIssueCode.RUNTIME_CLOSE_FAILED
    with pytest.raises(ValueError):
        CleanupResult(status=CleanupStatus.NOT_REQUIRED, finished_at_us=10)
    with pytest.raises(ValueError):
        CleanupResult(status=CleanupStatus.FAILED, finished_at_us=11)

def test_runner_error_requires_finite_phase_and_optional_stable_cause() -> None:
    from product.protocols import RunnerError

    error = RunnerError(
        code="TARGET_EXECUTION_FAILED",
        phase=RunnerFailurePhase.TARGET,
        cause_code="EXEC_TIMEOUT",
        retryable=False,
    )

    assert error.phase is RunnerFailurePhase.TARGET
    assert error.cause_code == "EXEC_TIMEOUT"
