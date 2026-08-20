# =============================================================================
# Serve 单实例锁
#
# 定位
#   同一 var 目录只能由一个本地控制面管理的资源所有权边界
#
# 职责
#   原子获取系统文件锁｜记录诊断 owner｜在退出时精确释放锁文件
#
# 边界
#   锁的有效性只由操作系统句柄决定；异常退出由内核释放，不按 PID 猜测抢占。
#
# 调用链
#   CLI serve → ServeLock → var directory lock file
# =============================================================================

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from product.backend.core.errors import ErrorCode, JiejianError


def _try_lock_stream(stream: BinaryIO) -> bool:
    """非阻塞获取首字节文件锁；锁是否有效只由操作系统句柄决定。"""

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


def _unlock_stream(stream: BinaryIO) -> None:
    """释放当前进程持有的文件锁；进程异常退出时由内核完成同一动作。"""

    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@dataclass(slots=True)
class ServeLock:
    """用进程持有的系统文件锁表示当前控制面对 var 目录的所有权。"""

    path: Path
    acquired: bool = False
    _stream: BinaryIO | None = None

    @classmethod
    def acquire(cls, var_dir: Path) -> ServeLock:
        """非阻塞获取系统锁；遗留诊断文件不会阻止异常退出后的自动恢复。"""

        path = var_dir.resolve() / ".serve.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = cls(path)
        stream: BinaryIO | None = None
        try:
            stream = path.open("a+b")
            if not _try_lock_stream(stream):
                stream.close()
                stream = None
                raise JiejianError(
                    ErrorCode.SERVE_FAILED,
                    "var 目录已被本地服务锁定；请先关闭正在运行的界鉴窗口",
                )
            payload = json.dumps(
                {"schema_version": "1", "lock_kind": "file-range", "pid": os.getpid()},
                separators=(",", ":"),
            ).encode("utf-8")
            stream.seek(0)
            stream.write(payload)
            stream.truncate()
            stream.flush()
            lock._stream = stream
            stream = None
            lock.acquired = True
            return lock
        except JiejianError:
            raise
        except OSError:
            if stream is not None:
                stream.close()
            raise JiejianError(ErrorCode.SERVE_FAILED, "本地服务锁不可创建") from None

    def release(self) -> None:
        """释放系统锁并清理诊断文件；重复调用不产生副作用。"""

        if not self.acquired:
            return
        stream = self._stream
        self._stream = None
        try:
            if stream is not None:
                try:
                    _unlock_stream(stream)
                finally:
                    stream.close()
            self.path.unlink(missing_ok=True)
        finally:
            self.acquired = False
