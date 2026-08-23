from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.onboarding.models import FolderSelectionResult
from product.backend.workflows.onboarding.workflow import OnboardingWorkflow, SystemFolderSelector
from tests.fixtures.runtime_environment import runtime_identity_environment


class FakeFolderSelector:
    def __init__(self, result: FolderSelectionResult) -> None:
        self.result = result

    def select_folder(self) -> FolderSelectionResult:
        return self.result


def test_service_preserves_cancelled_and_unavailable_selector_states() -> None:
    cancelled = OnboardingWorkflow(
        FakeFolderSelector(FolderSelectionResult(status="cancelled"))
    )
    unavailable = OnboardingWorkflow(
        FakeFolderSelector(
            FolderSelectionResult(
                status="unavailable",
                message="请改用手工绝对路径",
            )
        )
    )

    assert cancelled.select_folder().status == "cancelled"
    assert unavailable.select_folder().status == "unavailable"
    assert unavailable.select_folder().path is None


def test_service_inspect_is_explicit_and_read_only(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi", encoding="utf-8")
    service = OnboardingWorkflow(
        FakeFolderSelector(FolderSelectionResult(status="cancelled"))
    )

    result = service.inspect(str(tmp_path.resolve()))

    assert "Python" in result.detected_types
    assert not any(tmp_path.glob("*.out"))


def test_system_selector_reports_unavailable_without_starting_process() -> None:
    calls: list[object] = []
    result = SystemFolderSelector(
        platform_name="posix",
        runner=lambda *args, **kwargs: calls.append((args, kwargs)),
    ).select_folder()

    assert result.status == "unavailable"
    assert result.path is None
    assert calls == []


def test_system_selector_runs_bounded_process_with_controlled_desktop_environment(
    tmp_path: Path,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "schema_version": "1",
                    "status": "selected",
                    "path": "D:\\apps\\demo",
                }
            ),
            stderr="",
        )

    result = SystemFolderSelector(
        environment=runtime_identity_environment(
            tmp_path / "var",
            extra={
                "PATH": "C:\\Windows",
                "SYSTEMROOT": "C:\\Windows",
                "SystemDrive": "C:",
                "ProgramData": "C:\\ProgramData",
                "SECRET_TOKEN": "must-not-propagate",
            },
        ),
        timeout_seconds=2.0,
        python_executable=sys.executable,
        platform_name="nt",
        runner=runner,
    ).select_folder()

    assert result.status == "selected"
    assert result.path == "D:\\apps\\demo"
    command, kwargs = calls[0]
    assert command == [
        str(Path(sys.executable).resolve()),
        "-B",
        "-m",
        "product.backend.workflows.onboarding.folder_picker_process",
    ]
    assert kwargs["timeout"] == 2.0
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["cwd"] == str(Path(__file__).resolve().parents[4])
    assert kwargs["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert kwargs["env"]["SYSTEMDRIVE"] == "C:"
    assert kwargs["env"]["PROGRAMDATA"] == "C:\\ProgramData"
    assert "SECRET_TOKEN" not in kwargs["env"]


def test_system_selector_timeout_and_concurrent_request_return_unavailable() -> None:
    entered = threading.Event()
    release = threading.Event()
    completed: list[FolderSelectionResult] = []

    def blocking_runner(command, **kwargs):
        entered.set()
        assert release.wait(2)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"schema_version":"1","status":"cancelled"}',
            stderr="",
        )

    selector = SystemFolderSelector(platform_name="nt", runner=blocking_runner)
    worker = threading.Thread(target=lambda: completed.append(selector.select_folder()))
    worker.start()
    assert entered.wait(1)

    concurrent = selector.select_folder()
    release.set()
    worker.join(2)

    assert concurrent.status == "unavailable"
    assert "已经打开" in (concurrent.message or "")
    assert completed[0].status == "cancelled"
    assert not worker.is_alive()

    def timeout_runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    timed_out = SystemFolderSelector(
        platform_name="nt", runner=timeout_runner
    ).select_folder()
    assert timed_out.status == "unavailable"
    assert "超时" in (timed_out.message or "")


def test_system_selector_rejects_invalid_child_protocol() -> None:
    def runner(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    with pytest.raises(JiejianError) as captured:
        SystemFolderSelector(platform_name="nt", runner=runner).select_folder()

    assert captured.value.code == ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE.value
