# =============================================================================
# 运行时进程树控制
#
# 定位
#   为 Worker、Runner、Recording 和 Observer 提供统一的子进程树边界。
#
# 职责
#   Windows Job Object 绑定｜POSIX session/group 绑定｜有界终止与等待
#
# 边界
#   只管理进程生命周期，不解释任务业务结果；正常退出也必须释放控制句柄。
# =============================================================================

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os
import signal
import subprocess
import time
import weakref
from collections.abc import Callable, Mapping
from typing import Any

from product.backend.core.errors import ErrorCode, JiejianError


_CONTROLLERS: weakref.WeakKeyDictionary[subprocess.Popen[Any], ProcessTreeController] = (
    weakref.WeakKeyDictionary()
)
_NATIVE_POPEN = subprocess.Popen


class ProcessTreeController:
    """绑定一个子进程及其后代，并提供可证明的有界终止操作。"""

    def __init__(
        self,
        process: subprocess.Popen[Any],
        handle: int | None = None,
        process_group_id: int | None = None,
        kernel_identity: Mapping[str, str | int] | None = None,
    ) -> None:
        self.process = process
        self._job_handle = handle
        self._process_group_id = process_group_id
        self._kernel_identity = dict(kernel_identity or {})
        self._closed = False

    @classmethod
    def attach(
        cls,
        process: subprocess.Popen[Any],
        *,
        native: bool = True,
        tree_name: str | None = None,
    ) -> ProcessTreeController:
        existing = _CONTROLLERS.get(process)
        if existing is not None:
            return existing
        handle: int | None = None
        process_group_id: int | None = None
        kernel_identity: dict[str, str | int] = {}
        if native and os.name == "nt":
            handle = _create_kill_on_close_job(tree_name)
            try:
                if handle is None or not _assign_job(handle, int(process.pid)):
                    raise OSError("无法把子进程加入 Windows Job Object")
            except Exception:
                if handle is not None:
                    _close_handle(handle)
                raise
            if tree_name is not None:
                kernel_identity = {"kind": "windows-job", "name": tree_name}
        elif native:
            # spawn_managed_process 总是建立新 session，因此组 ID 等于根 PID；即使根先退出仍可按组回收后代。
            process_group_id = int(process.pid)
            kernel_identity = {
                "kind": "posix-process-group",
                "process_group_id": process_group_id,
            }
        controller = cls(process, handle, process_group_id, kernel_identity)
        _CONTROLLERS[process] = controller
        return controller

    @property
    def kernel_identity(self) -> dict[str, str | int]:
        """返回可持久化的内核树身份；PID 只在 POSIX 进程组语义下使用。"""

        return dict(self._kernel_identity)

    def has_exited(self) -> bool:
        """只有内核进程树为空时才返回 True；根 PID 退出本身不构成证明。"""

        if self._closed:
            return self.process.poll() is not None
        if os.name == "nt" and self._job_handle is not None:
            return _active_job_processes(self._job_handle) == 0
        if self._process_group_id is not None:
            return not _process_group_exists(self._process_group_id)
        return self.process.poll() is not None

    def terminate(self, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        if os.name == "nt" and self._job_handle is not None:
            if _active_job_processes(self._job_handle):
                _terminate_job(self._job_handle)
            self._wait_for_tree_exit(deadline)
            self._wait_for_root(deadline)
            self.close()
            return
        if self._process_group_id is not None:
            self._terminate_process_group(deadline)
            self._wait_for_root(deadline)
            self.close()
            return
        if self.process.poll() is None:
            try:
                self.process.terminate()
            except OSError:
                pass
            try:
                self.process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=max(0.0, deadline - time.monotonic()))
        self.close()

    def release(self, timeout: float) -> None:
        """正常根进程结束后确认后代也已退出；残留后代会被强制回收。"""

        if not self.has_exited():
            self.terminate(timeout)
            return
        self.close()

    def _terminate_process_group(self, deadline: float) -> None:
        group_id = self._process_group_id
        if group_id is None:
            return
        if _process_group_exists(group_id):
            try:
                os.killpg(group_id, signal.SIGTERM)
            except ProcessLookupError:
                return
        grace_deadline = min(deadline, time.monotonic() + 1.0)
        while _process_group_exists(group_id) and time.monotonic() < grace_deadline:
            time.sleep(0.01)
        if _process_group_exists(group_id):
            try:
                os.killpg(group_id, signal.SIGKILL)
            except ProcessLookupError:
                return
        self._wait_for_tree_exit(deadline)

    def _wait_for_tree_exit(self, deadline: float) -> None:
        while not self.has_exited():
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(
                    getattr(self.process, "args", self.process.pid),
                    max(0.0, deadline - time.monotonic()),
                )
            time.sleep(0.01)

    def _wait_for_root(self, deadline: float) -> None:
        if self.process.poll() is None:
            self.process.wait(timeout=max(0.0, deadline - time.monotonic()))

    def close(self) -> None:
        if self._closed:
            return
        if os.name == "nt" and self._job_handle is not None:
            _close_handle(self._job_handle)
            self._job_handle = None
        self._closed = True


def spawn_managed_process(
    command: list[str] | tuple[str, ...],
    *,
    popen: Callable[..., subprocess.Popen[Any]] = _NATIVE_POPEN,
    tree_name: str | None = None,
    **kwargs: Any,
) -> subprocess.Popen[Any]:
    """启动并立即绑定进程树；调用方仍可通过原 Popen 句柄等待或读取结果。"""

    if os.name == "nt":
        flags = int(kwargs.pop("creationflags", 0))
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        kwargs["creationflags"] = flags
    else:
        kwargs.setdefault("start_new_session", True)
    process = popen(command, **kwargs)
    try:
        ProcessTreeController.attach(
            process,
            native=popen is _NATIVE_POPEN,
            tree_name=tree_name,
        )
    except Exception:
        # 绑定失败时不得让已启动的根进程脱离监督继续运行。
        try:
            process.kill()
            process.wait(timeout=2.0)
        except Exception:
            pass
        raise
    return process


def controller_for(process: subprocess.Popen[Any]) -> ProcessTreeController | None:
    return _CONTROLLERS.get(process)


def release_process_tree(process: subprocess.Popen[Any], timeout: float = 2.0) -> None:
    controller = _CONTROLLERS.get(process)
    if controller is None:
        return
    try:
        controller.release(timeout)
        controller.close()
    except Exception as exc:
        raise JiejianError(
            ErrorCode.PROCESS_TREE_FAILED,
            "子进程树未能在有界时间内完成释放",
        ) from exc
    # 只有清理与句柄关闭全部成功才撤销所有权，失败保留同一控制器供调用方重试。
    _CONTROLLERS.pop(process, None)


def terminate_process_tree(process: subprocess.Popen[Any], timeout: float) -> None:
    controller = _CONTROLLERS.get(process)
    if controller is None:
        # 未经本模块启动的进程没有可证明的 Job/session 所有权，只能退回根进程回收。
        controller = ProcessTreeController(process)
        _CONTROLLERS[process] = controller
    try:
        controller.terminate(timeout)
        controller.close()
    except Exception as exc:
        raise JiejianError(
            ErrorCode.PROCESS_TREE_FAILED,
            "子进程树未能在有界时间内终止",
        ) from exc
    _CONTROLLERS.pop(process, None)


def process_tree_has_exited(process: subprocess.Popen[Any]) -> bool:
    """返回当前受控树的内核退出事实；未注册进程只检查根进程。"""

    controller = controller_for(process)
    return controller.has_exited() if controller is not None else process.poll() is not None


def kernel_tree_has_exited(identity: Mapping[str, object]) -> bool:
    """从持久内核身份确认旧执行树为空；无效或平台不匹配的身份一律拒绝。"""

    kind = identity.get("kind")
    if kind == "windows-job" and os.name == "nt":
        name = identity.get("name")
        if not isinstance(name, str) or not name:
            return False
        handle = _open_job(name)
        if handle is None:
            return True
        try:
            return _active_job_processes(handle) == 0
        finally:
            _close_handle(handle)
    if kind == "posix-process-group" and os.name != "nt":
        group_id = identity.get("process_group_id")
        return type(group_id) is int and group_id > 0 and not _process_group_exists(group_id)
    return False


def _process_group_exists(group_id: int) -> bool:
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


if os.name == "nt":

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimitInformation),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _BasicAccountingInformation(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _KERNEL32.CreateJobObjectW.restype = wintypes.HANDLE
    _KERNEL32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _KERNEL32.SetInformationJobObject.restype = wintypes.BOOL
    _KERNEL32.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _KERNEL32.OpenJobObjectW.restype = wintypes.HANDLE
    _KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _KERNEL32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _KERNEL32.AssignProcessToJobObject.restype = wintypes.BOOL
    _KERNEL32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _KERNEL32.TerminateJobObject.restype = wintypes.BOOL
    _KERNEL32.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _KERNEL32.QueryInformationJobObject.restype = wintypes.BOOL
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL


def _create_kill_on_close_job(name: str | None = None) -> int | None:
    if os.name != "nt":
        return None
    handle = _KERNEL32.CreateJobObjectW(None, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    info = _ExtendedLimitInformation()
    info.BasicLimitInformation.LimitFlags = 0x2000
    if not _KERNEL32.SetInformationJobObject(
        handle,
        9,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        error = ctypes.get_last_error()
        _close_handle(int(handle))
        raise ctypes.WinError(error)
    return int(handle)


def _open_job(name: str) -> int | None:
    if os.name != "nt":
        return None
    handle = _KERNEL32.OpenJobObjectW(0x0004, False, name)
    if handle:
        return int(handle)
    error = ctypes.get_last_error()
    if error in {2, 123}:
        return None
    raise ctypes.WinError(error)


def _assign_job(handle: int, pid: int) -> bool:
    if os.name != "nt":
        return False
    # AssignProcessToJobObject 要求 PROCESS_SET_QUOTA 与 PROCESS_TERMINATE。
    process_handle = _KERNEL32.OpenProcess(0x0100 | 0x0001, False, pid)
    if not process_handle:
        return False
    try:
        return bool(_KERNEL32.AssignProcessToJobObject(handle, process_handle))
    finally:
        _close_handle(int(process_handle))


def _terminate_job(handle: int) -> None:
    if os.name == "nt" and not _KERNEL32.TerminateJobObject(handle, 1):
        raise ctypes.WinError(ctypes.get_last_error())


def _active_job_processes(handle: int) -> int:
    if os.name != "nt":
        return 0
    info = _BasicAccountingInformation()
    returned = wintypes.DWORD()
    if not _KERNEL32.QueryInformationJobObject(
        handle,
        1,
        ctypes.byref(info),
        ctypes.sizeof(info),
        ctypes.byref(returned),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(info.ActiveProcesses)


def _close_handle(handle: int) -> None:
    if os.name == "nt" and not _KERNEL32.CloseHandle(handle):
        raise ctypes.WinError(ctypes.get_last_error())
