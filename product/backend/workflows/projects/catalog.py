# Project 应用服务：读取正式应用接入流程已经建立的产品身份。

from __future__ import annotations

from collections.abc import Callable

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.storage import ProjectRecord, StorageUnitOfWork


class ProjectCatalog:
    """提供项目列表与查询；创建和分析统一由应用接入服务负责。"""

    def __init__(self, uow_factory: Callable[..., StorageUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def list(self, *, include_archived: bool = False) -> tuple[ProjectRecord, ...]:
        with self._uow_factory() as work:
            records = work.projects.list_all()
        if include_archived:
            return records
        return tuple(item for item in records if item.status is not ProjectStatus.ARCHIVED)

    def get(self, project_id: str) -> ProjectRecord:
        with self._uow_factory() as work:
            record = work.projects.get(project_id)
        if record is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
        return record

    def current_observations(self, project_id: str) -> tuple[str, ...]:
        """为契约治理提供当前项目已经接入的最小观察能力。"""

        self.get(project_id)
        return ("resource_state",)
