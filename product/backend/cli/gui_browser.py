# GUI 复用受控 Chromium 和独立配置；当前服务只拥有自己启动的浏览器树。
from __future__ import annotations

import logging
import os
import subprocess
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.tree import spawn_managed_process, release_process_tree, terminate_process_tree

logger = logging.getLogger("jiejian.cli.gui_browser")


def _request_window_close(process: subprocess.Popen) -> bool:
    """只向仍存活的本次根进程窗口发送关闭消息，让 Chromium 保存界面偏好。"""
    if os.name != "nt" or process.poll() is not None:
        return False
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    requested = False

    @callback_type
    def visit(window, _):
        nonlocal requested
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        # 进程句柄仍存活才使用 PID，不能把已复用的 PID 当作窗口所有权。
        if pid.value == process.pid and process.poll() is None and user32.IsWindowVisible(window):
            requested = bool(user32.PostMessageW(window, 0x0010, 0, 0)) or requested
        return True

    user32.EnumWindows(visit, 0)
    return requested


def _close_owned_browser(process: subprocess.Popen) -> None:
    try:
        requested = _request_window_close(process)
    except OSError:
        requested = False
    if requested:
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass
    # 复用统一 Job/session 控制器；根已退出时也核对并收口其后代。
    if process.poll() is None:
        terminate_process_tree(process, timeout=3.0)
    else:
        release_process_tree(process, timeout=3.0)


class GuiBrowserSession:
    """保存当前服务的专用浏览器所有权；不管理系统浏览器或交接给已有实例的窗口。"""

    def __init__(self) -> None:
        self._owned: list[subprocess.Popen] = []
        self._closed = False
        self._lock = threading.Lock()

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def adopt(self, process: subprocess.Popen) -> bool:
        with self._lock:
            if self._closed:
                _close_owned_browser(process)
                return False
            self._owned.append(process)
            return True

    def close(self) -> None:
        with self._lock:
            self._closed = True
            # 成功后才撤销句柄；关闭失败仍保留同一所有权，不能改按名称清理。
            for process in tuple(self._owned):
                _close_owned_browser(process)
                self._owned.remove(process)


def open_gui_browser(url: str, var_dir: Path, *, session: GuiBrowserSession, system_browser: bool = False) -> bool:
    """打开本地 GUI；受控浏览器缺失或启动失败时回退系统浏览器，不安装新浏览器。"""
    if session.closed:
        return False
    address = urlsplit(url)
    if address.scheme != "http" or address.hostname != "127.0.0.1" or address.username or address.password:
        return False
    if not system_browser:
        executable = os.environ.get("JIEJIAN_PLAYWRIGHT_EXECUTABLE")
        if executable and Path(executable).is_file():
            try:
                profile = RuntimePaths(var_dir.resolve()).gui_browser
                profile.mkdir(parents=True, exist_ok=True)
                process = spawn_managed_process(
                    [str(Path(executable).resolve()), f"--user-data-dir={profile}",
                     "--disable-extensions", "--disable-infobars", "--no-first-run", "--no-default-browser-check",
                     f"--app={url}"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    close_fds=True,
                )
                try:
                    code = process.wait(timeout=0.6)
                except subprocess.TimeoutExpired:
                    return session.adopt(process)
                # 已有实例接收请求后只释放本次转交进程，不取得原浏览器的所有权。
                release_process_tree(process)
                if code == 0:
                    return True
            except OSError:
                pass
        logger.info("受控 GUI 浏览器不可用，改用系统浏览器", extra={"event_code": "GUI_BROWSER_FALLBACK"})
    try:
        return bool(webbrowser.open(url))
    except (OSError, webbrowser.Error):
        return False
