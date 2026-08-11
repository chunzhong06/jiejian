"""本地 serve 的单实例锁，避免两个控制面同时管理同一 var 目录。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from ..errors import ErrorCode, JiejianError


@dataclass(slots=True)
class ServeLock:
    path: Path
    acquired: bool = False

    @classmethod
    def acquire(cls, var_dir: Path) -> ServeLock:
        path = var_dir.resolve() / ".serve.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = cls(path)
        try:
            with path.open("x", encoding="utf-8") as stream:
                json.dump({"schema_version": "1", "pid": os.getpid()}, stream, separators=(",", ":"))
            lock.acquired = True
            return lock
        except FileExistsError:
            raise JiejianError(
                ErrorCode.SERVE_FAILED,
                "var 目录已被本地服务锁定；如进程已结束，请检查陈旧 .serve.lock",
            ) from None
        except OSError:
            raise JiejianError(ErrorCode.SERVE_FAILED, "本地服务锁不可创建") from None

    def release(self) -> None:
        if self.acquired:
            try:
                self.path.unlink(missing_ok=True)
            finally:
                self.acquired = False
