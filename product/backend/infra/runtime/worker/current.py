# 1.1.0 当前 Worker 生命周期占位监督器；不领取旧 Job，也不导入延期 ExecutionRequest/Runner。

from __future__ import annotations


class CurrentWorkerSupervisor:
    """只维护 serve 生命周期 ready 事实；执行能力恢复前不会消费任何持久 Job。"""

    def __init__(self, *args, **kwargs) -> None:
        _ = args, kwargs
        self._running = False

    def start(self) -> None:
        self._running = True

    def is_running(self) -> bool:
        return self._running

    @property
    def recovered_jobs(self) -> int:
        return 0

    def stop(self, timeout: float = 5.0) -> None:
        _ = timeout
        self._running = False


__all__ = ["CurrentWorkerSupervisor"]
