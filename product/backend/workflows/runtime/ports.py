# 按持久项目归属选择运行提供方；读取不启动目标，未知与冲突不能回退到示例。
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.runtime.runtime_identity import ControlledRuntimeReference
from product.protocols.runtime.node_runtime import NodeRuntimeReference

RuntimeReference = ControlledRuntimeReference | NodeRuntimeReference


@dataclass(frozen=True)
class RuntimeProvider:
    name: str
    owns_project: Callable[[str], bool]
    read: Callable[[str], RuntimeReference | None]
    load: Callable[[str, str], RuntimeReference]


class ProjectRuntimePorts:
    """组合根显式提供适配器；业务服务不识别 Sample 或根据端口猜测运行所有权。"""

    def __init__(self, providers: tuple[RuntimeProvider, ...]):
        if len({provider.name for provider in providers}) != len(providers):
            raise ValueError("runtime provider names must be unique")
        self._providers = providers

    def _owner(self, project_id: str) -> RuntimeProvider | None:
        matches = tuple(provider for provider in self._providers if provider.owns_project(project_id))
        if len(matches) > 1:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "运行所属来源存在冲突，请核对应用配置",
                details={"reason": "RUNTIME_PROVIDER_CONFLICT"})
        return matches[0] if matches else None

    def reference(self, project_id: str) -> RuntimeReference | None:
        owner = self._owner(project_id)
        return None if owner is None else owner.read(project_id)

    def load_delivery(self, project_id: str, source_fingerprint: str) -> RuntimeReference:
        owner = self._owner(project_id)
        if owner is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "当前应用尚未配置受支持的运行方式",
                details={"reason": "RUNTIME_PROVIDER_UNAVAILABLE"})
        # 提供方失败必须保留原错误；不能尝试其他应用或另一种启动方式。
        return owner.load(project_id, source_fingerprint)
