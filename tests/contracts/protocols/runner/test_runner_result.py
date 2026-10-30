# 验证 RunnerResult、cleanup 与稳定错误边界。

from __future__ import annotations
import pytest
from product.protocols.runner.result import CleanupResult, CleanupIssue, RunnerResult
from product.protocols.runner.input import CleanupIssueCode, CleanupStatus, RunnerFailurePhase
pytestmark = pytest.mark.level2

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
    from product.protocols.runner.result import RunnerError

    error = RunnerError(
        code="TARGET_EXECUTION_FAILED",
        phase=RunnerFailurePhase.TARGET,
        cause_code="EXEC_TIMEOUT",
        retryable=False,
    )

    assert error.phase is RunnerFailurePhase.TARGET
    assert error.cause_code == "EXEC_TIMEOUT"
