# 验证命令行入口中的运行提交。

from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from product.backend.cli.commands import runs as run_commands
from product.backend.core.lifecycle import RunVerdict
from product.protocols import RunnerResultType


class FakeRunnerResult:
    result_type = RunnerResultType.SUCCESS
    verdict = RunVerdict.PASS

    def model_dump(self, *, mode: str) -> dict[str, str]:
        assert mode == "json"
        return {"schema_version": "1", "verdict": self.verdict.value}


class FakeExecutionWorkflow:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run_profile(self, source_path: Path, **kwargs):
        self.calls.append({"source_path": source_path, **kwargs})
        return FakeRunnerResult()


class FakeApplication:
    def __init__(self, *args, **kwargs) -> None:
        self.execution = FakeExecutionWorkflow()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_run_uses_current_permission_workflow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    application = FakeApplication()
    @contextmanager
    def scope(*_args, **_kwargs):
        try:
            yield application
        finally:
            application.close()
    monkeypatch.setattr(run_commands, "application_scope", scope)
    source = tmp_path / "profile.json"

    run_commands.run_command(None, source, accept_source_changes=True)

    assert application.execution.calls == [{
        "source_path": source,
        "accept_source_changes": True,
        "idempotency_key": application.execution.calls[0]["idempotency_key"],
    }]
    assert application.closed is True
