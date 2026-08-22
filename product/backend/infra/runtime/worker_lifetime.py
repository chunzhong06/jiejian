# =============================================================================
# Worker 生存期锁
#
# 定位
#   Worker 执行进程与控制面异常恢复之间的系统级退出证明
#
# 职责
#   约束锁文件路径｜拒绝同任务重复进程｜形成旧 Worker 已退出的恢复证明
#
# 边界
#   PID 和诊断 JSON 不决定锁是否有效；只有内核锁可重新获取才允许恢复任务。
# =============================================================================

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from product.backend.core.identifiers import JOB_ID_PATTERN
from product.backend.infra.runtime.process_lock import lock_is_available, try_lock_stream, unlock_stream


def worker_lifetime_path(var_dir: Path, job_id: str) -> Path:
    """把受约束 Job ID 映射到 VarDir 内固定的 Worker 锁文件。"""

    import re

    if re.fullmatch(JOB_ID_PATTERN, job_id) is None:
        raise ValueError("Worker 任务 ID 无效")
    return var_dir.resolve() / "runtime" / "workers" / f"{job_id}.lock"


@dataclass(slots=True)
class WorkerLifetimeLock:
    path: Path
    _stream: BinaryIO
    acquired: bool = True

    @classmethod
    def acquire(cls, var_dir: Path, job_id: str, lease_owner: str) -> WorkerLifetimeLock:
        """在 Worker 进入 claim 前持有锁，拒绝同一 Job 的重复进程。"""

        path = worker_lifetime_path(var_dir, job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        stream = path.open("r+b")
        if not try_lock_stream(stream):
            stream.close()
            raise RuntimeError("同一任务已有 Worker 进程")
        payload = json.dumps(
            {
                "schema_version": "1",
                "lock_kind": "file-range",
                "job_id": job_id,
                "lease_owner": lease_owner,
                "pid": os.getpid(),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        stream.seek(0)
        stream.write(b"\0" + payload)
        stream.truncate()
        stream.flush()
        return cls(path=path, _stream=stream)

    @staticmethod
    def execution_has_exited(var_dir: Path, job_id: str) -> bool:
        """只有系统锁已可获取时才形成“旧 Worker 已退出”的恢复证明。"""

        path = worker_lifetime_path(var_dir, job_id)
        existed = path.exists()
        available = lock_is_available(path)
        if available and not existed:
            path.unlink(missing_ok=True)
        return available

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            unlock_stream(self._stream)
        finally:
            self._stream.close()
            self.acquired = False
