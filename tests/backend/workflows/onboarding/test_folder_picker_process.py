# 验证首次使用工作流中的目录选择子进程。

from __future__ import annotations

import json
from types import SimpleNamespace

from product.backend.workflows.onboarding import folder_picker_process


class FakeRoot:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.destroyed = False

    def withdraw(self) -> None:
        self.calls.append(("withdraw", None))

    def overrideredirect(self, value: bool) -> None:
        self.calls.append(("overrideredirect", value))

    def geometry(self, value: str) -> None:
        self.calls.append(("geometry", value))

    def attributes(self, name: str, value: object) -> None:
        self.calls.append((name, value))

    def deiconify(self) -> None:
        self.calls.append(("deiconify", None))

    def lift(self) -> None:
        self.calls.append(("lift", None))

    def focus_force(self) -> None:
        self.calls.append(("focus_force", None))

    def update(self) -> None:
        self.calls.append(("update", None))

    def destroy(self) -> None:
        self.destroyed = True


def test_dialog_has_explicit_foreground_parent_and_always_cleans_up() -> None:
    root = FakeRoot()
    options: dict[str, object] = {}

    def askdirectory(**kwargs):
        options.update(kwargs)
        return "D:\\apps\\demo"

    selected = folder_picker_process.show_directory_dialog(
        platform_name="nt",
        tk_module=SimpleNamespace(Tk=lambda: root),
        filedialog_module=SimpleNamespace(askdirectory=askdirectory),
    )

    assert selected == "D:\\apps\\demo"
    assert options == {
        "parent": root,
        "title": "选择要检查的应用文件夹",
        "mustexist": True,
    }
    assert ("-topmost", True) in root.calls
    assert ("focus_force", None) in root.calls
    assert root.destroyed is True


def test_process_protocol_maps_desktop_failure_to_stable_unavailable(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        folder_picker_process,
        "show_directory_dialog",
        lambda: (_ for _ in ()).throw(RuntimeError("private desktop detail")),
    )

    assert folder_picker_process.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema_version": "1",
        "status": "unavailable",
        "message": "系统目录选择器当前不可用，请改用手工绝对路径",
    }
