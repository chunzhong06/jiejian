# 服务就绪后的终端快捷操作；重开当前 GUI，退出交给现有服务清理流程。
from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from threading import Event
from contextlib import contextmanager


def console_key_reader() -> Callable[[], str | None] | None:
    """只读取 Windows 交互终端；重定向输入和无终端启动不消费 stdin。"""

    if os.name != "nt" or sys.stdin is None or not sys.stdin.isatty():
        return None
    import msvcrt

    def read_key() -> str | None:
        if not msvcrt.kbhit():
            return None
        key = msvcrt.getwch()
        if key in {"\x00", "\xe0"}:
            msvcrt.getwch()
            return None
        return key.lower()

    return read_key


@contextmanager
def console_input_mode(enabled: bool):
    if not enabled:
        yield
        return
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel.GetStdHandle.restype = wintypes.HANDLE
    kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handle, mode = kernel.GetStdHandle(-10), wintypes.DWORD()
    if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
        raise OSError(ctypes.get_last_error(), 'console input unavailable')
    # Ctrl+C 作为按键交给服务，避免同一控制台里的 CMD 收到信号后询问是否终止批处理。
    if not kernel.SetConsoleMode(handle, mode.value & ~1):
        raise OSError(ctypes.get_last_error(), 'console input mode unavailable')
    try:
        yield
    finally:
        kernel.SetConsoleMode(handle, mode.value)


@contextmanager
def launcher_key_reader(event_name: str | None):
    """便携 exe 的重复启动只发送本会话事件，复用当前服务打开 GUI 的动作。"""
    if event_name is None:
        yield None
        return
    import ctypes
    import re
    from ctypes import wintypes
    if os.name != 'nt' or os.environ.get('JIEJIAN_RUNTIME_MODE') != 'portable' or not re.fullmatch(r'Local\\JieJian-Reopen-[0-9a-f]{16}', event_name):
        raise ValueError('invalid portable launcher event')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.OpenEventW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenEventW(0x00100000, False, event_name)
    if not handle:
        raise OSError('portable launcher event unavailable')
    try:
        yield lambda: 'g' if kernel.WaitForSingleObject(handle, 0) == 0 else None
    finally:
        kernel.CloseHandle(handle)


def run_gui_console(
    *,
    open_browser: Callable[[], bool],
    stopped: Event,
    is_stopping: Callable[[], bool],
    emit: Callable[[str], None],
    shutdown: Callable[[], None] | None = None,
    read_key: Callable[[], str | None] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """处理 G 重开和 Ctrl+C/Q 退出；只读终端输入，不建立第二个控制面。"""

    reader = read_key or console_key_reader()
    if reader is None or stopped.is_set() or is_stopping():
        return
    try:
        with console_input_mode(read_key is None):
            _run_controls(reader, open_browser, stopped, is_stopping, emit, shutdown, monotonic)
    except (OSError, ValueError):
        emit("input-unavailable")


def _run_controls(reader, open_browser, stopped, is_stopping, emit, shutdown, monotonic):
    emit("controls-ready")
    next_open = 0.0
    while not stopped.wait(0.1) and not is_stopping():
        try:
            key = reader()
        except (OSError, ValueError):
            emit("input-unavailable")
            return
        if key is not None and key.lower() in {"\x03", "q"} and shutdown is not None:
            if stopped.is_set() or is_stopping():
                return
            emit("stopping")
            shutdown()
            stopped.wait()
            return
        if key is None or key.lower() != "g" or monotonic() < next_open:
            continue
        if stopped.is_set() or is_stopping():
            return
        # 启动调用串行完成；短时间的键盘自动重复不产生一串新窗口。
        next_open = monotonic() + 2.0
        try:
            opened = open_browser()
        except (OSError, ValueError):
            opened = False
        emit("opened" if opened else "open-failed")
