from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import CaseVerdict
from product.backend.infra.runtime.runner import composition
from product.protocols import (
    CleanupStatus,
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
    assert result.reason_codes == (ErrorCode.CLEANUP_FAILED.value,)
    assert result.evidence == ()
    assert result.artifacts == ()
