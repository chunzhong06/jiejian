# 内部 PermissionContract 版本链事务；不提供手工需求、候选或公共治理入口。

from __future__ import annotations

import time
from collections.abc import Callable

from product.backend.core.contracts.lifecycle import revise_contract_version, transition_contract_version
from product.backend.core.contracts.models import (
    ContractAuditAction,
    ContractAuditEntry,
    ContractProvenance,
    ContractVersion,
    SourceReference,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.verification.permissions import PermissionContract
from product.backend.infra.storage import StorageUnitOfWork


class ContractGovernance:
    """维护确定性 Compiler 生成的不可变 ContractVersion 版本链。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        clock_us: Callable[[], int] | None = None,
        available_observations: tuple[str, ...] | None = None,
        observer_resolver: Callable[[str], tuple[str, ...]] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
        self._available_observations = available_observations
        self._observer_resolver = observer_resolver

    def create_draft(
        self,
        project_id: str,
        contract_id: str,
        *,
        snapshot: PermissionContract,
        sources: tuple[SourceReference, ...] = (),
        actor: str,
    ) -> ContractVersion:
        """为内部生成契约创建首个 DRAFT，并只保存可追溯来源。"""

        now_us = self._clock_us()
        if snapshot.contract_id != contract_id or snapshot.version != 1:
            raise JiejianError(
                ErrorCode.CONTRACT_REFERENCE_INVALID,
                "初稿必须使用 contract_id 一致且 version=1 的完整契约",
            )
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            if work.contract_versions.list_for_contract(project_id, contract_id):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "契约已经存在")
            draft = ContractVersion(
                project_id=project_id,
                contract_id=contract_id,
                version=1,
                status=ContractStatus.DRAFT,
                snapshot=snapshot,
                provenance=self._provenance(sources),
                audit=(
                    ContractAuditEntry(
                        action=ContractAuditAction.CREATED,
                        actor=actor,
                        occurred_at_us=now_us,
                    ),
                ),
                created_at_us=now_us,
                updated_at_us=now_us,
            )
            work.contract_versions.add(draft)
            work.commit()
        return draft

    def revise_active(
        self,
        project_id: str,
        contract_id: str,
        *,
        snapshot: PermissionContract,
        sources: tuple[SourceReference, ...] = (),
        actor: str,
    ) -> ContractVersion:
        """从当前 ACTIVE 版本派生新的内部 DRAFT，旧版本保持不可变。"""

        now_us = self._clock_us()
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            active = work.contract_versions.get_active(project_id, contract_id)
            if active is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "没有可修订的 ACTIVE 契约")
            if snapshot.contract_id != contract_id or snapshot.version != active.version + 1:
                raise JiejianError(
                    ErrorCode.CONTRACT_REFERENCE_INVALID,
                    "修订必须显式提供下一版本完整契约",
                )
            revision = revise_contract_version(
                active,
                snapshot=snapshot,
                provenance=self._provenance(sources),
                actor=actor,
                occurred_at_us=now_us,
            )
            work.contract_versions.add(revision)
            work.commit()
        return revision

    def submit_review(
        self,
        project_id: str,
        contract_id: str,
        version: int,
        *,
        actor: str,
        available_observations: tuple[str, ...] | None = None,
    ) -> ContractVersion:
        return self._transition(
            project_id,
            contract_id,
            version,
            ContractStatus.REVIEW,
            actor,
            available_observations=available_observations,
        )

    def reject_review(
        self,
        project_id: str,
        contract_id: str,
        version: int,
        *,
        actor: str,
    ) -> ContractVersion:
        return self._transition(project_id, contract_id, version, ContractStatus.REJECTED, actor)

    def activate_review(
        self,
        project_id: str,
        contract_id: str,
        version: int,
        *,
        actor: str,
        available_observations: tuple[str, ...] | None = None,
    ) -> ContractVersion:
        now_us = self._clock_us()
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            reviewed = work.contract_versions.get(project_id, contract_id, version)
            if reviewed is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
            self._ensure_required_observations(
                reviewed,
                available_observations=available_observations,
            )
            active = work.contract_versions.get_active(project_id, contract_id)
            activated = transition_contract_version(
                reviewed,
                ContractStatus.ACTIVE,
                actor=actor,
                occurred_at_us=now_us,
            )
            if active is not None:
                work.contract_versions.replace(
                    transition_contract_version(
                        active,
                        ContractStatus.SUPERSEDED,
                        actor=actor,
                        occurred_at_us=now_us,
                    )
                )
            work.contract_versions.replace(activated)
            project = work.projects.get(project_id)
            if project is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            work.projects.replace(
                project.model_copy(
                    update={
                        "governed_contract_id": activated.contract_id,
                        "governed_contract_version": activated.version,
                        "updated_at_us": max(project.updated_at_us, now_us),
                    }
                )
            )
            work.commit()
        return activated

    def list_versions(self, project_id: str, contract_id: str) -> tuple[ContractVersion, ...]:
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            return work.contract_versions.list_for_contract(project_id, contract_id)

    def _transition(
        self,
        project_id: str,
        contract_id: str,
        version: int,
        target: ContractStatus,
        actor: str,
        *,
        available_observations: tuple[str, ...] | None = None,
    ) -> ContractVersion:
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            current = work.contract_versions.get(project_id, contract_id, version)
            if current is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
            if target is ContractStatus.REVIEW:
                self._ensure_required_observations(
                    current,
                    available_observations=available_observations,
                )
            updated = transition_contract_version(
                current,
                target,
                actor=actor,
                occurred_at_us=self._clock_us(),
            )
            work.contract_versions.replace(updated)
            work.commit()
        return updated

    def _ensure_required_observations(
        self,
        contract: ContractVersion,
        *,
        available_observations: tuple[str, ...] | None,
    ) -> None:
        observations = available_observations or self._available_observations
        if observations is None and self._observer_resolver is not None:
            observations = self._observer_resolver(contract.project_id)
        available = set(observations or ("resource_state",))
        missing = sorted(
            {
                requirement
                for rule in contract.snapshot.rules
                for requirement in rule.required_observations
                if requirement not in available
            }
        )
        if missing:
            raise JiejianError(
                ErrorCode.CONTRACT_ASSESSMENT_BLOCKED,
                "契约需要的观察方式当前不可用",
                details={"required_observations": missing},
            )

    @staticmethod
    def _require_project(work: StorageUnitOfWork, project_id: str) -> None:
        if work.projects.get(project_id) is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")

    @staticmethod
    def _provenance(sources: tuple[SourceReference, ...]) -> ContractProvenance:
        return ContractProvenance(
            sources=tuple(
                sorted(
                    set(sources),
                    key=lambda item: (
                        item.source_type.value,
                        item.locator,
                        item.content_sha256,
                    ),
                )
            )
        )
