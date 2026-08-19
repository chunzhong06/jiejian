# Project 应用服务：只保存产品身份、目标类型与治理绑定。

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ProjectStatus
from product.backend.infra.storage import ProjectRecord, StorageUnitOfWork
from product.protocols import ExecutionProfile, TargetType, parse_execution_profile


class ProjectCatalog:
    """维护 ProjectRecord；Profile 才是执行配置和治理引用的输入。"""

    def __init__(self, uow_factory: Callable[..., StorageUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    def list(self) -> tuple[ProjectRecord, ...]:
        with self._uow_factory() as work:
            return work.projects.list_all()

    def get(self, project_id: str) -> ProjectRecord:
        with self._uow_factory() as work:
            record = work.projects.get(project_id)
        if record is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
        return record

    def register(
        self,
        profile_path: Path,
    ) -> tuple[ProjectRecord, ExecutionProfile]:
        try:
            profile = parse_execution_profile(profile_path.resolve().read_bytes())
        except OSError:
            raise JiejianError(ErrorCode.EXECUTION_PROFILE_INVALID, "当前执行 Profile 不可读取") from None
        if profile.target_type is not TargetType.WEB:
            raise JiejianError(ErrorCode.PROJECT_TARGET_INVALID, "当前项目只允许 WEB 目标")
        now_us = time.time_ns() // 1_000
        with self._uow_factory() as work:
            existing = work.projects.get(profile.project_id)
            if existing is not None and existing.target_type is not profile.target_type:
                raise JiejianError(ErrorCode.PROJECT_TARGET_INVALID, "项目目标类型不能漂移")
            record = ProjectRecord(
                project_id=profile.project_id,
                name=profile.project_name,
                status=ProjectStatus.READY,
                target_type=profile.target_type,
                governed_contract_id=existing.governed_contract_id if existing else None,
                governed_contract_version=existing.governed_contract_version if existing else None,
                created_at_us=existing.created_at_us if existing else now_us,
                updated_at_us=max(now_us, existing.updated_at_us) if existing else now_us,
            )
            if existing is None:
                work.projects.add(record)
            else:
                work.projects.replace(record)
            work.commit()
        return record, profile

    def current_contract(self, project_id: str):
        record = self.get(project_id)
        if record.governed_contract_id is None or record.governed_contract_version is None:
            raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "项目尚未绑定 ACTIVE 契约版本")
        with self._uow_factory() as work:
            contract = work.contract_versions.get(
                project_id,
                record.governed_contract_id,
                record.governed_contract_version,
            )
        if contract is None or contract.status.value != "ACTIVE":
            raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "项目绑定的契约版本不是 ACTIVE")
        return contract

    def current_observations(self, project_id: str) -> tuple[str, ...]:
        self.get(project_id)
        return ("resource_state",)
