# =============================================================================
# ExecutionRequest 构造
#
# 定位
#   当前 ProjectBundle 与治理 Contract 进入新 Run 冻结快照的应用边界
#
# 职责
#   读取当前项目｜解析 ACTIVE 或显式兼容 Contract｜构造路径无关请求
#
# 调用链
#   API / CLI → ExecutionRequestService → Projects / contracts.execution_binding
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..contracts.execution_binding import resolve_execution_contract
from ..verification.models import SecurityContract
from ..projects.service import ProjectControlService
from ..protocols import ExecutionBudgetV1, ExecutionProjectSnapshotV1
from ..storage import StorageUnitOfWork
from ..verification.inputs import ProjectBundle
from .request_store import PersistedExecutionRequestV1


def build_execution_request(
    bundle: ProjectBundle,
    *,
    flow: Any = None,
    contract: SecurityContract | None = None,
) -> PersistedExecutionRequestV1:
    project = bundle.project
    selected_flow = flow or bundle.flow
    selected_contract = contract or bundle.contract
    snapshot = ExecutionProjectSnapshotV1(
        schema_version="1",
        project_id=project.id,
        project_name=project.name,
        target=project.target,
        identities=project.identities,
        resources=project.resources,
        flow=selected_flow,
        contract=selected_contract,
        owner_observer_enabled=project.owner_observer_enabled,
        mutation_seed=project.mutation_seed,
    )
    duration = min(
        max(int(project.target.timeout_seconds * project.target.max_requests * 1_000_000), 1),
        3_600_000_000,
    )
    return PersistedExecutionRequestV1(
        schema_version="1",
        budget=ExecutionBudgetV1(
            schema_version="1",
            max_requests=project.target.max_requests,
            request_timeout_us=int(project.target.timeout_seconds * 1_000_000),
            max_duration_us=duration,
            max_response_bytes=project.target.max_response_bytes,
            max_parallel_cases=1,
        ),
        project_snapshot=snapshot,
    )


class ExecutionRequestService:
    """组合已校验项目、治理绑定和执行请求协议。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        projects: ProjectControlService,
    ) -> None:
        self._uow_factory = uow_factory
        self._projects = projects

    def execution_request(
        self, project_id: str, *, flow: Any = None
    ) -> PersistedExecutionRequestV1:
        record, bundle = self._projects.current_bundle(project_id)
        contract = resolve_execution_contract(
            self._uow_factory,
            record,
            bundle.contract,
        )
        return build_execution_request(bundle, flow=flow, contract=contract)
