# 隔离 Runner 的稳定执行器入口；具体编排由 execution 模块承担。

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

from product.backend.infra.runtime.runner.execution import execute_attempt


def execute_runner_attempt(
    input_path: Path,
    staging_dir: Path,
    *,
    environ: Mapping[str, str] | None = None,
    finished_at_us: Callable[[], int] | None = None,
) -> int:
    """执行唯一当前 Permission Runner 请求。"""

    return execute_attempt(
        input_path,
        staging_dir,
        environ=environ,
        finished_at_us=finished_at_us,
    )
