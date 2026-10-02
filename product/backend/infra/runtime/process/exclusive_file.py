# Windows 独占文件句柄：拒绝其他句柄读写/删除记录文件，不将 Node 权限当作 SQLite 文件隔离。
from __future__ import annotations

import os
from pathlib import Path


def open_exclusive_record_file(path: Path):
    """返回拥有 OS 独占句柄的二进制文件；不支持的平台不降级为普通可共享文件。"""
    if os.name != 'nt' or path.resolve() != path.absolute() or path.is_symlink():
        raise OSError('exclusive record file unavailable')
    import msvcrt
    import win32file
    import win32con
    import pywintypes
    try:
        handle = win32file.CreateFile(str(path), win32con.GENERIC_READ | win32con.GENERIC_WRITE,
            0, None, win32con.OPEN_ALWAYS, win32con.FILE_ATTRIBUTE_NORMAL, None)
    except pywintypes.error:
        raise OSError('exclusive record file unavailable') from None
    native = handle.Detach()
    try:
        descriptor = msvcrt.open_osfhandle(native, os.O_RDWR | os.O_BINARY)
    except BaseException:
        win32file.CloseHandle(native)
        raise
    return os.fdopen(descriptor, 'r+b', buffering=0)
