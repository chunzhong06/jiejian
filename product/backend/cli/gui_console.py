# 服务就绪后的终端快捷操作；只重新打开当前 GUI，不创建第二个控制面或改变检查任务。
from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from threading import Event


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


def run_gui_console(
    *,
    open_browser: Callable[[], bool],
    stopped: Event,
    is_stopping: Callable[[], bool],
    emit: Callable[[str], None],
    read_key: Callable[[], str | None] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> None:
    """在同一服务内处理 G；停止事件结束等待，重复按键不并发打开浏览器。"""

    reader = read_key or console_key_reader()
    if reader is None or stopped.is_set() or is_stopping():
        return
    emit("controls-ready")
    next_open = 0.0
    while not stopped.wait(0.1) and not is_stopping():
        try:
            key = reader()
        except (OSError, ValueError):
            emit("input-unavailable")
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
