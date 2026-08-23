# =============================================================================
# Target Runtime Registry
#
# 定位
#   Runner 组合入口与具体 Target Runtime Factory 之间的确定性注册表。
#
# 职责
#   校验 bounded kind｜拒绝重复与未知类型｜验证 Factory 返回的 Runtime 端口
#
# 边界
#   不导入或默认注册任何 Web/未来 Target 实现。
#
# 调用链
#   runner/composition → TargetRuntimeRegistry → TargetRuntimeFactory
# =============================================================================

from __future__ import annotations

import re

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.execution.port import (
    ExecutionSnapshotView,
    TargetRuntime,
    TargetRuntimeContext,
    TargetRuntimeFactory,
)


_KIND = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


class TargetRuntimeRegistry:
    """保存当前进程显式注册的 Target Runtime Factory。"""

    def __init__(self) -> None:
        self._factories: dict[str, TargetRuntimeFactory] = {}

    def register(self, factory: TargetRuntimeFactory) -> None:
        kind = getattr(factory, "kind", None)
        if not isinstance(kind, str) or _KIND.fullmatch(kind) is None:
            raise ValueError("target runtime kind must be a bounded stable string")
        if not callable(getattr(factory, "create", None)):
            raise TypeError("target runtime factory must provide create")
        if kind in self._factories:
            raise ValueError(f"target runtime kind already registered: {kind}")
        self._factories[kind] = factory

    def create(
        self,
        kind: str,
        snapshot: ExecutionSnapshotView,
        context: TargetRuntimeContext,
    ) -> TargetRuntime:
        factory = self._factories.get(kind)
        if factory is None:
            raise JiejianError(ErrorCode.EXEC_REQUEST, "执行目标类型未注册")
        runtime = factory.create(snapshot, context)
        if not isinstance(runtime, TargetRuntime):
            raise TypeError("target runtime factory returned an invalid runtime")
        return runtime

    def factory(self, kind: str) -> TargetRuntimeFactory:
        """返回已注册 Factory，供组合根把同一注册事实注入通用 Executor。"""

        factory = self._factories.get(kind)
        if factory is None:
            raise JiejianError(ErrorCode.EXEC_REQUEST, "执行目标类型未注册")
        return factory
