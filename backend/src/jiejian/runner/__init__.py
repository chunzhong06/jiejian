"""隔离 Runner 的稳定进程入口与执行边界。"""

from .execution import (
    RUNNER_EXIT_INTERNAL,
    RUNNER_EXIT_OK,
    RUNNER_EXIT_PROTOCOL,
    RUNNER_EXIT_WRITE,
    execute_runner_attempt,
)

__all__ = [
    "RUNNER_EXIT_INTERNAL",
    "RUNNER_EXIT_OK",
    "RUNNER_EXIT_PROTOCOL",
    "RUNNER_EXIT_WRITE",
    "execute_runner_attempt",
]
