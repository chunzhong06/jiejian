# =============================================================================
# 进程生存期文件锁
#
# 定位
#   Serve 与 Worker 共享的操作系统级存活事实
#
# 职责
#   非阻塞获取首字节锁｜显式释放锁｜探测当前是否存在锁持有者
#
# 边界
#   锁句柄是唯一有效性事实；文件内容和 PID 只用于诊断，不参与存活判断。
# =============================================================================

from __future__ import annotations

import os
from pathlib import Path
from typing import BinaryIO


def try_lock_stream(stream: BinaryIO) -> bool:
    """非阻塞锁定首字节；进程异常退出时由内核自动释放。"""

    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"\0")
        stream.flush()
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def unlock_stream(stream: BinaryIO) -> None:
    """释放当前句柄持有的首字节锁。"""

    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def lock_is_available(path: Path) -> bool:
    """只探测当前是否存在生存期持有者，不读取或相信文件中的 PID。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        if not try_lock_stream(stream):
            return False
        unlock_stream(stream)
        return True
    finally:
        stream.close()
