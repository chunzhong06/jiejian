# =============================================================================
# 共享 Observer 注册表
#
# 定位
#   Runner 组合根与共享 Observer Adapter 之间的显式注册边界。
#
# 职责
#   保存 Observer 执行器｜拒绝重复注册｜提供稳定查找。
#
# 边界
#   不导入 Web、HTTP、Cookie、OAuth 或 Target Runtime；OWNER_API 由 Case
#   Session 通过 Target Runtime Port 处理。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable

from product.protocols.observer import ObserverType


ObserverExecutor = Callable[..., object]


class ObserverRegistry:
    """保存共享、无 Target 专属状态的 Observer 执行器。"""

    def __init__(self) -> None:
        self._executors: dict[ObserverType, ObserverExecutor] = {}

    def register(self, observer_type: ObserverType, executor: ObserverExecutor) -> None:
        if observer_type in self._executors:
            raise ValueError(f"observer type already registered: {observer_type.value}")
        if not callable(executor):
            raise TypeError("observer executor must be callable")
        self._executors[observer_type] = executor

    def get(self, observer_type: ObserverType) -> ObserverExecutor | None:
        return self._executors.get(observer_type)

