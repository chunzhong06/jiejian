# 验证隔离 Runner 运行时中的执行尝试完成。

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict
from product.backend.infra.runtime.runner import composition
from product.backend.infra.execution.web import runtime as web_runtime
from product.backend.infra.execution.port import TargetCleanupIssue
from product.backend.infra.runtime.runner.case_orchestrator import CaseExecutionFailure
from product.protocols import (
    CleanupIssueCode,
    CleanupStatus,
    RunnerFailurePhase,
    RunnerResultType,
    canonical_runner_json_bytes,
    parse_runner_result,
)
from tests.fixtures.runner import evidence, runner_input


def _write_input(path: Path) -> None:
    path.write_bytes(canonical_runner_json_bytes(runner_input()))


@pytest.mark.parametrize(
    ("failure", "expected_type"),
    (
        (None, RunnerResultType.SUCCESS),
        (ErrorCode.EXEC_CANCELLED, RunnerResultType.CANCELLED),
        (ErrorCode.SCOPE_URL, RunnerResultType.SAFETY_STOPPED),
        ("RUNNER_FATAL", RunnerResultType.FATAL_ERROR),
    ),
)
def test_attempt_closes_runtime_before_reading_final_times(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: ErrorCode | str | None,
    expected_type: RunnerResultType,
) -> None:
    events: list[str] = []

    class _Executor:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def run_case(self, *_args, **_kwargs):
            events.append("case")
            if isinstance(failure, ErrorCode):
                raise JiejianError(failure, "测试失败")
            if failure is not None:
                raise RuntimeError("测试失败")
            return SimpleNamespace(verdict=CaseVerdict.SAFE)

        def close(self) -> None:
            events.append("close")

    ticks = iter((1000, 1001))

    def clock() -> int:
        events.append("clock")
        return next(ticks)

    monkeypatch.setattr(composition, "RunnerExecutor", _Executor)
    monkeypatch.setattr(
        composition,
        "evidence_from_case",
        lambda *_args, **_kwargs: evidence(),
    )
    input_path = tmp_path / "input.json"
    staging = tmp_path / "staging"
    _write_input(input_path)

    exit_code = composition.execute_attempt(
        input_path,
        staging,
        environ={
            "JIEJIAN_TEST_TOKEN": "subject-secret",
            "OWNER_READ_ONLY": "owner-secret",
        },
        finished_at_us=clock,
    )
    result = parse_runner_result((staging / "result.json").read_bytes())

    assert exit_code == composition.RUNNER_EXIT_OK
    assert events[-3:] == ["close", "clock", "clock"]
    assert result.result_type is expected_type
    assert result.cleanup.finished_at_us == 1000
    assert result.finished_at_us == 1001


def test_runtime_close_failure_overrides_staged_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class _Executor:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def run_case(self, *_args, **_kwargs):
            events.append("case")
            return SimpleNamespace(verdict=CaseVerdict.SAFE)

        def close(self) -> None:
            events.append("close")
            raise RuntimeError("close failed")

    ticks = iter((2000, 2001))

    def clock() -> int:
        events.append("clock")
        return next(ticks)

    monkeypatch.setattr(composition, "RunnerExecutor", _Executor)
    monkeypatch.setattr(
        composition,
        "evidence_from_case",
        lambda *_args, **_kwargs: evidence(),
    )
    input_path = tmp_path / "input.json"
    staging = tmp_path / "staging"
    _write_input(input_path)

    exit_code = composition.execute_attempt(
        input_path,
        staging,
        environ={
            "JIEJIAN_TEST_TOKEN": "subject-secret",
            "OWNER_READ_ONLY": "owner-secret",
        },
        finished_at_us=clock,
    )
    result = parse_runner_result((staging / "result.json").read_bytes())

    assert exit_code == composition.RUNNER_EXIT_OK
    assert events[-3:] == ["close", "clock", "clock"]
    assert any((staging / "artifacts" / "evidence").glob("*.json"))
    assert result.result_type is RunnerResultType.FATAL_ERROR
    assert result.cleanup.status is CleanupStatus.FAILED
    assert result.cleanup.finished_at_us == 2000
    assert result.finished_at_us == 2001
    assert result.error is not None
    assert result.error.code == ErrorCode.CLEANUP_FAILED.value
    assert result.error.phase is RunnerFailurePhase.RUNTIME_CLOSE
    assert result.reason_codes == (ErrorCode.CLEANUP_FAILED.value,)
    assert result.cleanup.issues[0].code is CleanupIssueCode.RUNTIME_CLOSE_FAILED
    assert result.evidence == ()
    assert result.artifacts == ()


def test_attempt_preserves_primary_target_failure_when_cleanup_also_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Executor:
        def __init__(self, *_args, **_kwargs) -> None:
            return None

        def run_case(self, *_args, **_kwargs):
            cause = JiejianError(ErrorCode.EXEC_TIMEOUT, "目标请求超时")
            primary = JiejianError(
                ErrorCode.TARGET_EXECUTION_FAILED,
                "TARGET 请求失败",
            )
            primary.__cause__ = cause
            raise CaseExecutionFailure(
                primary,
                RunnerFailurePhase.TARGET,
                (
                    TargetCleanupIssue(
                        CleanupIssueCode.POST_CASE_RECOVERY_FAILED,
                        ErrorCode.TARGET_UNREACHABLE.value,
                    ),
                ),
            )

        def close(self) -> None:
            return None

    monkeypatch.setattr(composition, "RunnerExecutor", _Executor)
    input_path = tmp_path / "input.json"
    staging = tmp_path / "staging"
    _write_input(input_path)

    assert composition.execute_attempt(
        input_path,
        staging,
        environ={
            "JIEJIAN_TEST_TOKEN": "subject-secret",
            "OWNER_READ_ONLY": "owner-secret",
        },
    ) == composition.RUNNER_EXIT_OK
    result = parse_runner_result((staging / "result.json").read_bytes())

    assert result.error is not None
    assert result.error.code == ErrorCode.TARGET_EXECUTION_FAILED.value
    assert result.error.phase is RunnerFailurePhase.TARGET
    assert result.error.cause_code == ErrorCode.EXEC_TIMEOUT.value
    assert result.cleanup.issues[0].code is CleanupIssueCode.POST_CASE_RECOVERY_FAILED


def test_attempt_rejects_control_origin_as_target_without_network(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.json"
    staging = tmp_path / "staging"
    _write_input(input_path)

    assert composition.execute_attempt(
        input_path,
        staging,
        environ={
            "JIEJIAN_TEST_TOKEN": "subject-secret",
            "OWNER_READ_ONLY": "owner-secret",
            "JIEJIAN_CONTROL_ORIGIN": "http://127.0.0.1:8765",
        },
    ) == composition.RUNNER_EXIT_OK
    result = parse_runner_result((staging / "result.json").read_bytes())

    assert result.result_type is RunnerResultType.SAFETY_STOPPED
    assert result.reason_codes == (ErrorCode.SELF_TARGET_FORBIDDEN.value,)
    assert result.error is None
    assert result.cleanup.status is CleanupStatus.SUCCEEDED


def test_prepare_recovery_failure_keeps_unreachable_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_recovery(*_args, **_kwargs) -> None:
        raise JiejianError(ErrorCode.TARGET_UNREACHABLE, "目标服务不可达")

    monkeypatch.setattr(
        web_runtime.HttpExecutionAdapter,
        "cleanup",
        fail_recovery,
    )
    input_path = tmp_path / "input.json"
    staging = tmp_path / "staging"
    _write_input(input_path)

    assert composition.execute_attempt(
        input_path,
        staging,
        environ={
            "JIEJIAN_TEST_TOKEN": "subject-secret",
            "OWNER_READ_ONLY": "owner-secret",
        },
    ) == composition.RUNNER_EXIT_OK
    result = parse_runner_result((staging / "result.json").read_bytes())

    assert result.verdict is None
    assert result.error is not None
    assert result.error.code == ErrorCode.PREPARE_RECOVERY_FAILED.value
    assert result.error.phase is RunnerFailurePhase.PREPARE_RECOVERY
    assert result.error.cause_code == ErrorCode.TARGET_UNREACHABLE.value
    assert result.cleanup.issues[0].code is CleanupIssueCode.POST_CASE_RECOVERY_FAILED
