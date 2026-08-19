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
import time
from pathlib import Path

from product.backend.workflows.context import WorkerContext
from product.backend.core.lifecycle import JobState
from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.logging import configure_logging

logger = logging.getLogger("jiejian.runtime.worker_process")


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m product.backend.infra.runtime.worker_process")
    parser.add_argument("--var-dir", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--lease-owner", required=True)
    arguments = parser.parse_args()
    var_dir = arguments.var_dir.resolve()
    var_dir.mkdir(parents=True, exist_ok=True)
    configure_logging(var_dir=var_dir)
    context = WorkerContext(var_dir, environ=os.environ)
    try:
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
        context.close()


if __name__ == "__main__":
    raise SystemExit(main())
