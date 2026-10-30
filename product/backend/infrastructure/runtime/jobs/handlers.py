# Execution JobHandler 端口
# 定义 JobHandler、按 Job target 惰性注册 Handler
# Registry 只做显式类型分派，不提供隐式 fallback 或跨 target 结果转换。

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.storage import JobRecord
from product.backend.infrastructure.runtime.jobs.targets import JobTargetType

ResultT_co = TypeVar("ResultT_co", covariant=True)


class JobHandler(Protocol[ResultT_co]):
    """一个作业处理器的稳定执行端口。"""

    def run_job(self, job_id: str) -> ResultT_co | None:
        ...




class JobHandlerRegistry:
    """按 Job 目标类型惰性创建单任务 Handler。"""

    def __init__(self) -> None:
        self._factories: dict[JobTargetType, Callable[[], JobHandler[Any]]] = {}
        self._operation_types: dict[JobTargetType, frozenset[str]] = {}
        self._auxiliary_factories: dict[str, Callable[[], JobHandler[Any]]] = {}

    def register(
        self,
        target_type: JobTargetType,
        factory: Callable[[], JobHandler[Any]],
        *,
        operation_types: frozenset[str] | None = None,
    ) -> None:
        if not isinstance(target_type, JobTargetType):
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务目标类型非法")
        if target_type in self._factories:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务处理器重复注册")
        self._factories[target_type] = factory
        if operation_types is not None:
            self._operation_types[target_type] = operation_types

    def register_auxiliary(
        self,
        name: str,
        factory: Callable[[], JobHandler[Any]],
    ) -> None:
        """注册不占用持久 Job target 的 Worker 辅助 Handler。"""

        if not isinstance(name, str) or not name or not name.isascii() or not name.replace("_", "").isalnum() or name != name.upper():
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "辅助任务处理器名称非法")
        if name in self._auxiliary_factories:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "辅助任务处理器重复注册")
        self._auxiliary_factories[name] = factory

    def resolve_auxiliary(self, name: str) -> JobHandler[Any]:
        try:
            factory = self._auxiliary_factories[name]
        except KeyError:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "辅助任务处理器未注册") from None
        return factory()

    def resolve(self, job: JobRecord) -> JobHandler[Any]:
        target_type = JobTargetType.from_job(job)
        # RUN 是持久目标类型，不能据此接受已退出当前链路的旧执行操作。
        allowed = self._operation_types.get(target_type)
        if allowed is not None and job.operation_type not in allowed:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务操作类型未注册")
        try:
            factory = self._factories[target_type]
        except KeyError:
            raise JiejianError(ErrorCode.JOB_PERSISTENCE, "任务处理器未注册") from None
        return factory()
