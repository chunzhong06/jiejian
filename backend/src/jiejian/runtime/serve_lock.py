# =============================================================================
# Serve 单实例锁
#
# 定位
#   同一 var 目录只能由一个本地控制面管理的资源所有权边界
#
# 职责
#   原子获取锁｜识别陈旧 owner｜在退出时精确释放锁文件
#
# 调用链
#   CLI serve → ServeLock → var directory lock file
# =============================================================================

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
