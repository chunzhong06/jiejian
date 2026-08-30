# 自动 L5 的 Windows UI Automation 边界：唯一定位 Recording Chromium 并通过 InvokePattern 操作真实业务控件。

from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from pathlib import Path

from pywinauto import Desktop
from pywinauto.base_wrapper import BaseWrapper
from pywinauto.application import WindowSpecification


_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SAMPLE_TITLE = "协作空间 · 校园数字展馆"


class WindowsL5Error(RuntimeError):
    """只发布稳定、无秘密的 Windows 自动 L5 错误码。"""


@dataclass(frozen=True, slots=True)
class WindowFact:
    """用于证明 Recording 窗口来自本轮受控 Chromium 的顶层窗口事实。"""

    handle: int
    process_id: int
    title: str
    image: Path


def _process_image(process_id: int) -> Path | None:
    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_bool
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not handle:
        return None
    try:
        size = ctypes.c_ulong(32_768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return Path(buffer.value).resolve()
    finally:
        kernel32.CloseHandle(handle)


def visible_top_level_windows() -> tuple[WindowFact, ...]:
    """返回当前 UIA 可见顶层窗口及其真实进程映像，不改变窗口前台状态。"""

    facts: list[WindowFact] = []
    for window in Desktop(backend="uia").windows():
        try:
            if not window.is_visible():
                continue
            process_id = int(window.process_id())
            image = _process_image(process_id)
            if image is None:
                continue
            facts.append(
                WindowFact(
                    handle=int(window.handle),
                    process_id=process_id,
                    title=window.window_text(),
                    image=image,
                )
            )
        except (OSError, RuntimeError):
            continue
    return tuple(facts)


def window_snapshot() -> frozenset[int]:
    """冻结 Recording 提交前已经存在的可见顶层窗口句柄。"""

    return frozenset(item.handle for item in visible_top_level_windows())


def _exists(window: WindowSpecification, title: str, control_type: str) -> bool:
    return window.child_window(title=title, control_type=control_type).exists(timeout=0.1)


def _wait_control(
    window: WindowSpecification,
    title: str,
    control_type: str,
    *,
    timeout: float,
    allow_repeated_text: bool = False,
) -> BaseWrapper:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        criteria: dict[str, object] = {"title": title, "control_type": control_type}
        if allow_repeated_text:
            # 同一只读状态可同时出现在项目概览与导出详情；动作按钮仍必须保持唯一。
            criteria["found_index"] = 0
        control = window.child_window(**criteria)
        if control.exists(timeout=0.1):
            return control.wrapper_object()
        time.sleep(0.2)
    raise WindowsL5Error("RECORDING_UI_NOT_READY")


def _wait_text(window: WindowSpecification, title: str, *, timeout: float) -> None:
    _wait_control(
        window,
        title,
        "Text",
        timeout=timeout,
        allow_repeated_text=True,
    )


def _invoke_button(window: WindowSpecification, title: str, *, timeout: float = 15) -> None:
    button = _wait_control(window, title, "Button", timeout=timeout)
    invoke = getattr(button, "invoke", None)
    if not callable(invoke):
        raise WindowsL5Error("RECORDING_UI_INVOKE_UNAVAILABLE")
    invoke()


class RecordingWindowDriver:
    """用新窗口、映像、标题和 Sample 可访问性树联合证明并操作 Recording 窗口。"""

    def __init__(self, before: frozenset[int], chromium_executable: Path) -> None:
        self._before = before
        self._chromium = chromium_executable.resolve()
        self._window: WindowSpecification | None = None

    def wait_until_ready(self, *, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        candidate_seen = False
        desktop = Desktop(backend="uia")
        while time.monotonic() < deadline:
            candidates = [
                item
                for item in visible_top_level_windows()
                if item.handle not in self._before
                and _SAMPLE_TITLE in item.title
                and str(item.image).casefold() == str(self._chromium).casefold()
            ]
            if len(candidates) > 1:
                raise WindowsL5Error("RECORDING_WINDOW_AMBIGUOUS")
            if len(candidates) == 1:
                candidate_seen = True
                window = desktop.window(handle=candidates[0].handle)
                if _exists(window, "进入项目", "Button"):
                    self._window = window
                    return
            time.sleep(0.2)
        if candidate_seen:
            raise WindowsL5Error("RECORDING_UI_NOT_READY")
        raise WindowsL5Error("RECORDING_WINDOW_NOT_FOUND")

    def run_business_flow(self) -> None:
        """只在 capture.started 后 Invoke 正式页面按钮，并等待可访问性状态闭合。"""

        if self._window is None:
            raise WindowsL5Error("RECORDING_WINDOW_NOT_FOUND")
        _invoke_button(self._window, "进入项目")
        _invoke_button(self._window, "生成完整资料包")
        _wait_text(self._window, "完整项目资料包已生成。", timeout=20)
        _invoke_button(self._window, "撤销本次导出")
        _invoke_button(self._window, "确认撤销")
        _wait_text(self._window, "已撤销", timeout=15)
        _wait_control(self._window, "重新生成资料包", "Button", timeout=15)
