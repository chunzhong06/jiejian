# =============================================================================
# 通用执行路由
#
# 只按冻结的 TargetType 选择适配器；当前发布版本仅注册 Web adapter。
# =============================================================================

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.verification.facts import ExecutionFact, TargetType
from product.protocols.runner import ActionExecutionBinding


class ExecutionAdapter(Protocol):
    target_type: TargetType

    def execute(
        self,
        binding: ActionExecutionBinding,
        *,
        case_id: str,
        action_id: str,
        bearer_token: str | None = None,
    ) -> ExecutionFact: ...

    def cleanup(self, path: str, *, case_id: str) -> None: ...


class ExecutionRouter:
    def __init__(self, adapters: Iterable[ExecutionAdapter] = ()) -> None:
        self._adapters: dict[TargetType, ExecutionAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: ExecutionAdapter) -> None:
        target_type = adapter.target_type
        if not isinstance(target_type, TargetType):
            raise ValueError("execution adapter target_type must be a TargetType")
        if target_type in self._adapters:
            raise ValueError(f"execution adapter already registered: {target_type.value}")
        self._adapters[target_type] = adapter

    def execute(
        self,
        target_type: TargetType,
        binding: ActionExecutionBinding,
        *,
        case_id: str,
        action_id: str,
        bearer_token: str | None = None,
    ) -> ExecutionFact:
        adapter = self._adapters.get(target_type)
        if adapter is None:
            raise JiejianError(ErrorCode.EXEC_REQUEST, "执行目标类型未注册")
        return adapter.execute(
            binding,
            case_id=case_id,
            action_id=action_id,
            bearer_token=bearer_token,
        )

    def cleanup(self, target_type: TargetType, path: str, *, case_id: str) -> None:
        adapter = self._adapters.get(target_type)
        if adapter is None:
            raise JiejianError(ErrorCode.EXEC_REQUEST, "清理目标类型未注册")
        adapter.cleanup(path, case_id=case_id)
