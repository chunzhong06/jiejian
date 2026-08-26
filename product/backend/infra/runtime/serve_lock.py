# =============================================================================
# Serve 单实例锁
#
# 定位
#   同一 var 目录只能由一个本地控制面管理的资源所有权边界
#
# 职责
#   原子获取系统文件锁｜记录诊断 owner｜在退出时精确释放系统锁
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
from secrets import token_hex
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.process.lock import try_lock_stream, unlock_stream
from product.backend.infra.runtime.paths import RuntimePaths


@dataclass(slots=True)
class ServeLock:
    """用进程持有的系统文件锁表示当前控制面对 var 目录的所有权。"""

    path: Path
    owner_token: str = ""
    acquired: bool = False
    _stream: BinaryIO | None = None

    @classmethod
    def acquire(cls, var_dir: Path) -> ServeLock:
        """非阻塞获取系统锁；遗留诊断文件不会阻止异常退出后的自动恢复。"""

        path = RuntimePaths(var_dir).locks / "serve.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = cls(path)
        stream: BinaryIO | None = None
        try:
            path.touch(exist_ok=True)
            stream = path.open("r+b")
            if not try_lock_stream(stream):
                stream.close()
                stream = None
                raise JiejianError(
                    ErrorCode.SERVE_FAILED,
                    "var 目录已被本地服务锁定；请先关闭正在运行的界鉴窗口",
                )
            lock.owner_token = token_hex(16)
            payload = json.dumps(
                {
                    "schema_version": "1",
                    "lock_kind": "file-range",
                    "owner_token": lock.owner_token,
                    "pid": os.getpid(),
                },
                separators=(",", ":"),
            ).encode("utf-8")
            # 第 0 字节只承担系统锁；诊断 JSON 从第 1 字节开始，允许其他进程读取 token。
            stream.seek(0)
            stream.write(b"\0" + payload)
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
        """释放系统锁并保留诊断文件；重复调用不产生副作用。"""

        if not self.acquired:
            return
        stream = self._stream
        self._stream = None
        try:
            if stream is not None:
                try:
                    unlock_stream(stream)
                finally:
                    stream.close()
        finally:
            self.acquired = False
