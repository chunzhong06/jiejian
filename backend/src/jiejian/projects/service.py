# =============================================================================
# Project 控制服务
#
# 定位
#   Project bundle 接入、来源完整性和 TargetScope 解析的应用边界
#
# 职责
#   校验并登记 Project｜冻结来源摘要｜解析执行所需项目数据
#
# 调用链
#   CLI / API / Contract / Execution → ProjectControlService → Verification inputs / Storage
# =============================================================================

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from pathlib import Path
from ..domain.lifecycle import ContractStatus, ProjectStatus
from ..errors import ErrorCode, JiejianError
from ..storage import ProjectRecord, StorageUnitOfWork
from ..verification.inputs import ProjectBundle, load_contract, load_project_bundle


def file_sha256(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        raise JiejianError(ErrorCode.INPUT_FILE, "项目来源文件不可读取") from None


def project_source_hash(bundle: ProjectBundle) -> str:
    """绑定项目声明及其已解析 Flow 的路径与内容身份。"""

    digest = hashlib.sha256()
    for label, path in (
        ("project", bundle.project_file.resolve()),
        ("flow", bundle.project.flow_path.resolve()),
    ):
        digest.update(label.encode("ascii") + b"\0")
        digest.update(str(path).encode("utf-8") + b"\0")
        digest.update(file_sha256(path).encode("ascii") + b"\0")
    return digest.hexdigest()


class ProjectControlService:
    """维护项目来源身份；不读取 ContractVersion 或执行目标请求。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
    ) -> None:
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
        project_path: Path,
        *,
        contract_path: Path | None = None,
        revalidate: bool = False,
    ) -> tuple[ProjectRecord, ProjectBundle]:
        bundle = load_project_bundle(project_path, contract_path=contract_path)
        if bundle.contract.status is not ContractStatus.ACTIVE:
            raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "只有 ACTIVE 契约可以用于任务")
        source = bundle.project_file.resolve()
        selected_contract = bundle.project.contract_path.resolve()
        source_hash = project_source_hash(bundle)
        contract_hash = file_sha256(selected_contract)
        now_us = time.time_ns() // 1_000
        with self._uow_factory() as work:
            existing = work.projects.get(bundle.project.id)
            if existing is not None and (
                existing.source_hash != source_hash
                or existing.source_path != str(source)
                or existing.active_contract_path != str(selected_contract)
                or existing.active_contract_hash != contract_hash
            ) and not revalidate:
                raise JiejianError(
                    ErrorCode.PROJECT_SOURCE_DRIFT,
                    "项目来源或契约内容已变化，请显式重新校验",
                )
            record = ProjectRecord(
                project_id=bundle.project.id,
                name=bundle.project.name,
                status=ProjectStatus.READY,
                source_path=str(source),
                source_hash=source_hash,
                active_contract_path=str(selected_contract),
                active_contract_hash=contract_hash,
                governed_contract_id=existing.governed_contract_id if existing else None,
                governed_contract_version=existing.governed_contract_version if existing else None,
                created_at_us=existing.created_at_us if existing else now_us,
                updated_at_us=now_us,
            )
            if existing is None:
                work.projects.add(record)
            else:
                work.projects.replace(record)
            work.commit()
        return record, bundle

    def revalidate(self, project_id: str) -> tuple[ProjectRecord, ProjectBundle]:
        record = self.get(project_id)
        if not record.source_path or not record.active_contract_path:
            raise JiejianError(ErrorCode.PROJECT_NOT_REVALIDATED, "旧项目缺少来源，请重新注册")
        return self.register(
            Path(record.source_path),
            contract_path=Path(record.active_contract_path),
            revalidate=True,
        )

    def activate_contract(self, project_id: str, contract_path: Path) -> ProjectRecord:
        record = self.get(project_id)
        path = contract_path.resolve()
        contract = load_contract(path)
        if contract.status is not ContractStatus.ACTIVE:
            raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "只有 ACTIVE 契约可以激活")
        digest = file_sha256(path)
        now_us = time.time_ns() // 1_000
        updated = record.model_copy(
            update={
                "active_contract_path": str(path),
                "active_contract_hash": digest,
                "governed_contract_id": None,
                "governed_contract_version": None,
                "updated_at_us": max(now_us, record.updated_at_us),
            }
        )
        with self._uow_factory() as work:
            work.projects.replace(updated)
            work.commit()
        return updated

    def current_bundle(self, project_id: str) -> tuple[ProjectRecord, ProjectBundle]:
        record = self.get(project_id)
        if not record.source_path or not record.source_hash or not record.active_contract_path or not record.active_contract_hash:
            raise JiejianError(ErrorCode.PROJECT_NOT_REVALIDATED, "项目来源尚未完成 API 校验")
        source = Path(record.source_path)
        contract = Path(record.active_contract_path)
        try:
            bundle = load_project_bundle(source, contract_path=contract)
        except JiejianError:
            raise JiejianError(ErrorCode.PROJECT_SOURCE_DRIFT, "项目来源或契约内容已变化，请显式重新校验") from None
        if project_source_hash(bundle) != record.source_hash or file_sha256(contract) != record.active_contract_hash:
            raise JiejianError(ErrorCode.PROJECT_SOURCE_DRIFT, "项目来源或契约内容已变化，请显式重新校验")
        if bundle.contract.status is not ContractStatus.ACTIVE:
            raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "只有 ACTIVE 契约可以用于任务")
        return record, bundle

    def current_observers(self, project_id: str) -> tuple[str, ...]:
        """从当前已校验项目来源解析可用观察器。"""

        _, bundle = self.current_bundle(project_id)
        return ("http", "owner_api") if bundle.project.owner_observer_enabled else ("http",)
