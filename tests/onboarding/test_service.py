from __future__ import annotations

import builtins
from types import SimpleNamespace
from pathlib import Path

from jiejian.onboarding import service as service_module
from jiejian.onboarding.models import FolderSelectionResult
from jiejian.onboarding.service import OnboardingService, SystemFolderSelector


class FakeFolderSelector:
    def __init__(self, result: FolderSelectionResult) -> None:
        self.result = result

    def select_folder(self) -> FolderSelectionResult:
        return self.result


def test_service_preserves_cancelled_and_unavailable_selector_states() -> None:
    cancelled = OnboardingService(
        FakeFolderSelector(FolderSelectionResult(status="cancelled"))
    )
    unavailable = OnboardingService(
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
    service = OnboardingService(
        FakeFolderSelector(FolderSelectionResult(status="cancelled"))
    )

    result = service.inspect(str(tmp_path.resolve()))

    assert "Python" in result.detected_types
    assert not any(tmp_path.glob("*.out"))


def test_system_selector_reports_unavailable_without_importing_tkinter(
    monkeypatch,
) -> None:
    monkeypatch.setattr(service_module.os, "name", "posix")
    result = SystemFolderSelector().select_folder()
    assert result.status == "unavailable"
    assert result.path is None


def test_system_selector_imports_tkinter_only_when_called(monkeypatch) -> None:
    imports: list[str] = []
    filedialog = SimpleNamespace(askdirectory=lambda **kwargs: "")

    class FakeTk:
        def withdraw(self) -> None:
            pass

        def destroy(self) -> None:
            pass

    tkinter = SimpleNamespace(Tk=FakeTk, filedialog=filedialog)
    original_import = builtins.__import__

    def tracking_import(name, *args, **kwargs):
        if name == "tkinter":
            imports.append(name)
            return tkinter
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", tracking_import)
    monkeypatch.setattr(service_module.os, "name", "nt")
    selector = SystemFolderSelector()
    assert imports == []

    result = selector.select_folder()

    assert result.status == "cancelled"
    assert imports == ["tkinter", "tkinter"]
