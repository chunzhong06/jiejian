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
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from product.backend.core.identifiers import JOB_ID_PATTERN
from product.backend.infra.runtime.process.lock import lock_is_available, try_lock_stream, unlock_stream
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.process.tree import ProcessTreeController, kernel_tree_has_exited


def worker_lifetime_path(var_dir: Path, job_id: str) -> Path:
    """把受约束 Job ID 映射到 VarDir 内固定的 Worker 锁文件。"""

    import re

    if re.fullmatch(JOB_ID_PATTERN, job_id) is None:
        raise ValueError("Worker 任务 ID 无效")
    return RuntimePaths(var_dir).worker_runtime / f"{job_id}.lock"


def worker_tree_identity_path(var_dir: Path, job_id: str) -> Path:
    """返回与 Worker 锁并列的内核树身份收据路径。"""

    worker_lifetime_path(var_dir, job_id)
    return RuntimePaths(var_dir).worker_runtime / f"{job_id}.tree.json"


def worker_tree_name(job_id: str, lease_owner: str) -> str:
    """生成不含业务值且可由恢复方重算的 Windows Job Object 名称。"""

    worker_lifetime_path(Path("."), job_id)
    digest = hashlib.sha256(f"{job_id}\0{lease_owner}".encode("utf-8")).hexdigest()
    return f"Local\\JiejianWorker-{digest}"


def write_worker_tree_identity(
    var_dir: Path,
    job_id: str,
    lease_owner: str,
    controller: ProcessTreeController,
) -> None:
    """在启动闸门放行前原子保存可由内核重验的进程树身份。"""

    identity = controller.kernel_identity
    if not identity:
        # 注入 fake Popen 的单元测试不建立真实内核对象，也不得伪造恢复收据。
        return
    path = worker_tree_identity_path(var_dir, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    payload = {
        "schema_version": "1",
        "job_id": job_id,
        "lease_owner": lease_owner,
        "kernel_identity": identity,
    }
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temporary, path)


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
    def execution_has_exited(
        var_dir: Path,
        job_id: str,
        lease_owner: str | None = None,
    ) -> bool:
        """同时重验 Worker 锁与内核树收据；任一证据不足都拒绝恢复。"""

        path = worker_lifetime_path(var_dir, job_id)
        existed = path.exists()
        available = lock_is_available(path)
        if available and not existed:
            path.unlink(missing_ok=True)
        if not available or lease_owner is None:
            return False
        receipt_path = worker_tree_identity_path(var_dir, job_id)
        try:
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            identity = payload["kernel_identity"]
            if (
                payload.get("schema_version") != "1"
                or payload.get("job_id") != job_id
                or payload.get("lease_owner") != lease_owner
                or not isinstance(identity, dict)
            ):
                return False
            if os.name == "nt" and identity != {
                "kind": "windows-job",
                "name": worker_tree_name(job_id, lease_owner),
            }:
                return False
            return kernel_tree_has_exited(identity)
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            unlock_stream(self._stream)
        finally:
            self._stream.close()
            self.acquired = False
