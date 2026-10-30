# 启动独立 Worker 并持有日志、进程树和分发责任。
# 执行结果由各任务所属 reader 接受，分发成功不代表任务或权限检查成功。

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


from product.backend.domain.identifiers import JOB_ID_PATTERN
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.process.environment import ProcessEnvironmentRole, spawn_python_module
from product.backend.infrastructure.runtime.process.tree import release_process_tree, terminate_process_tree
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.runtime.worker.lifetime import write_worker_tree_identity, worker_tree_name

WORKER_LOG_MAX_BYTES = 1_048_576
WORKER_LOG_BACKUPS = 2


class WorkerDispatcher:
    """只启动当前Worker并管理其日志与进程树，不保留旧同步执行等待链。"""

    def __init__(
        self,
        *,
        var_dir: Path,
        environ: Mapping[str, str] | None = None,
        popen: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
    ) -> None:
        self.var_dir = var_dir.resolve()
        self._paths = RuntimePaths(self.var_dir).ensure_layout()
        self._environ = os.environ if environ is None else environ
        self._popen = popen

    def start(
        self,
        *,
        job_id: str,
        lease_owner: str,
        secret_names: Sequence[str],
    ) -> subprocess.Popen[Any]:
        """以最小环境启动独立 Worker；秘密仅通过受控名称解析，不继承完整父进程环境。"""

        source_environment = dict(self._environ)
        source_environment.setdefault("JIEJIAN_VAR_DIR", str(self.var_dir))
        source_environment.setdefault(
            "JIEJIAN_PYTHON_EXECUTABLE", str(Path(sys.executable).resolve())
        )
        source_environment.setdefault(
            "JIEJIAN_PYTHON_ENVIRONMENT_PATH", str(Path(sys.prefix).resolve())
        )
        source_environment.setdefault("JIEJIAN_PYTHON_ENVIRONMENT_TYPE", "当前 Python 环境")
        arguments = [
            "--var-dir",
            str(self.var_dir),
            "--job-id",
            job_id,
            "--lease-owner",
            lease_owner,
        ]
        for name in secret_names:
            arguments.extend(("--secret-name", name))
        log_path = self._prepare_worker_log(job_id)
        try:
            worker_log = log_path.open("ab", buffering=0)
            from product.backend.infrastructure.runtime.generated_files import register_generated_file
            register_generated_file(self.var_dir, log_path, 'worker-log')
        except OSError:
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "Worker 诊断日志无法打开",
            ) from None
        try:
            return spawn_python_module(
                source_environment,
                "product.backend.interfaces.worker.job",
                *arguments,
                role=ProcessEnvironmentRole.WORKER,
                secret_names=secret_names,
                cwd=self._paths.temp,
                popen=self._popen,
                tree_name=worker_tree_name(job_id, lease_owner),
                before_release=lambda _process, controller: write_worker_tree_identity(
                    self.var_dir,
                    job_id,
                    lease_owner,
                    controller,
                ),
                stdin=subprocess.DEVNULL,
                stdout=worker_log,
                stderr=worker_log,
                close_fds=True,
            )
        except (OSError, JiejianError):
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "独立 Worker 进程启动失败",
            ) from None
        finally:
            worker_log.close()

    def _prepare_worker_log(self, job_id: str) -> Path:
        """返回按 Job 可定位的有界日志，并在新 launch 前执行固定备份轮换。"""

        if re.fullmatch(JOB_ID_PATTERN, job_id) is None:
            raise JiejianError(ErrorCode.RUNNER_START_FAILED, "Worker 任务 ID 无效")
        root = RuntimePaths(self.var_dir).worker_logs.resolve()
        path = (root / f"{job_id}.log").resolve()
        if not path.is_relative_to(root):
            raise JiejianError(ErrorCode.RUNNER_START_FAILED, "Worker 日志路径越界")
        try:
            root.mkdir(parents=True, exist_ok=True)
            if path.is_file() and path.stat().st_size >= WORKER_LOG_MAX_BYTES:
                oldest = path.with_name(f"{path.name}.{WORKER_LOG_BACKUPS}")
                oldest.unlink(missing_ok=True)
                for index in range(WORKER_LOG_BACKUPS - 1, 0, -1):
                    source = path.with_name(f"{path.name}.{index}")
                    if source.is_file():
                        os.replace(source, path.with_name(f"{path.name}.{index + 1}"))
                os.replace(path, path.with_name(f"{path.name}.1"))
                from product.backend.infrastructure.runtime.generated_files import register_generated_file
                for backup in root.glob(f"{path.name}.*"):
                    register_generated_file(self.var_dir, backup, 'worker-log')
        except OSError:
            raise JiejianError(
                ErrorCode.RUNNER_START_FAILED,
                "Worker 诊断日志准备失败",
            ) from None
        return path






    @staticmethod
    def close_process(process: subprocess.Popen[Any] | None, timeout: float = 2.0) -> None:
        """结束同步调用者拥有的 Worker 整棵进程树；清理失败不得伪装为任务完成。"""

        if process is None:
            return
        try:
            if process.poll() is None:
                terminate_process_tree(process, timeout)
            else:
                release_process_tree(process, timeout)
        except Exception:
            raise JiejianError(
                ErrorCode.PROCESS_TREE_FAILED,
                "Worker 进程树未能完整退出",
            ) from None
