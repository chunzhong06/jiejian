# =============================================================================
# Worker 稳定进程入口
#
# 定位
#   jiejian.worker.runtime 的长期进程壳与 Execution 调度之间的组合边界
#
# 职责
#   解析单任务参数｜创建 ApplicationContext｜调度注册的 JobHandler
#
# 调用链
#   python -m jiejian.worker.runtime → ApplicationContext → WorkerDispatcher
# =============================================================================

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from ..application.context import ApplicationContext
from ..domain.lifecycle import JobState
from ..errors import JiejianError


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m jiejian.worker.runtime")
    parser.add_argument("--var-dir", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--lease-owner", required=True)
    arguments = parser.parse_args()
    var_dir = arguments.var_dir.resolve()
    var_dir.mkdir(parents=True, exist_ok=True)
    context = ApplicationContext(var_dir)
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
            except JiejianError:
                pass
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
        return 1
    finally:
        context.close()


if __name__ == "__main__":
    raise SystemExit(main())
