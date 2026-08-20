# =============================================================================
# Worker 稳定进程入口
#
# 定位
#   product.backend.infra.runtime.worker_process 的长期进程壳与 Execution 调度之间的组合边界
#
# 职责
#   解析单任务参数｜创建 ApplicationCore｜调度注册的 JobHandler
#
# 边界
#   进程入口不解释 Job 业务结果；退出码只表达调度完成或稳定失败类别。
#
# 调用链
#   python -m product.backend.infra.runtime.worker_process → ApplicationCore → WorkerDispatcher
# =============================================================================

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import TextIO

logger = logging.getLogger("jiejian.runtime.worker_process")


class _RedactingTextStream:
    """在结构化日志初始化前也替换已注入秘密，底层仍使用直接文件句柄。"""

    def __init__(self, stream: TextIO, secrets: tuple[str, ...]) -> None:
        self._stream = stream
        self._secrets = tuple(
            sorted({secret for secret in secrets if secret}, key=len, reverse=True)
        )

    def write(self, value: str) -> int:
        for secret in self._secrets:
            value = value.replace(secret, "[REDACTED]")
        return self._stream.write(value)

    def flush(self) -> None:
        self._stream.flush()

    @property
    def encoding(self) -> str | None:
        return self._stream.encoding


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m product.backend.infra.runtime.worker_process")
    parser.add_argument("--var-dir", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--lease-owner", required=True)
    parser.add_argument("--secret-name", action="append", default=[])
    arguments = parser.parse_args()
    known_secrets = tuple(
        value
        for name in arguments.secret_name
        if (value := os.environ.get(name))
    )
    # import、组合根与 handler 初始化的异常都先经过精确秘密替换，再落入每 Job 诊断日志。
    sys.stdout = _RedactingTextStream(sys.stdout, known_secrets)
    sys.stderr = _RedactingTextStream(sys.stderr, known_secrets)
    var_dir = arguments.var_dir.resolve()
    var_dir.mkdir(parents=True, exist_ok=True)
    from product.backend.infra.runtime.logging import configure_logging

    configure_logging(
        var_dir=var_dir,
        console=True,
        known_secrets=known_secrets,
    )
    context = None
    try:
        from product.backend.workflows.context import WorkerContext
        from product.backend.core.lifecycle import JobState
        from product.backend.core.errors import JiejianError

        context = WorkerContext(var_dir, environ=os.environ)
        with context.uow_factory() as work:
            initial_job = work.jobs.get(arguments.job_id)
        if initial_job is None:
            return 1
        handler = context.build_job_handler_registry(
            arguments.lease_owner,
            os.environ,
        ).resolve(initial_job)
        while True:
            try:
                handler.run_job(arguments.job_id)
            except JiejianError as exc:
                logger.error(
                    "job handler failed",
                    extra={"component": "worker_process", "event_code": "JOB_HANDLER_ERROR", "job_id": arguments.job_id, "error_code": exc.code},
                )
            with context.uow_factory() as work:
                job = work.jobs.get(arguments.job_id)
            if job is None:
                return 1
            if job.state in {JobState.SUCCEEDED, JobState.CANCELLED}:
                return 0
            if job.state is JobState.RETRY_WAIT and job.attempt < job.max_attempts:
                delay_us = max(job.available_at_us - time.time_ns() // 1_000, 0)
                time.sleep(delay_us / 1_000_000)
                continue
            return 1
    except Exception:
        logger.exception(
            "worker process exited unexpectedly",
            extra={"component": "worker_process", "event_code": "WORKER_PROCESS_ERROR", "job_id": arguments.job_id},
        )
        return 1
    finally:
        if context is not None:
            context.close()


if __name__ == "__main__":
    raise SystemExit(main())
