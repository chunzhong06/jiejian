# =============================================================================
# PermissionContract 治理
#
# 定位
# Requirement、Candidate 与唯一 Contract 版本链之间的事务应用服务。
#
# 职责
# 记录 provenance｜创建和修订版本｜执行审阅状态转换｜绑定 ACTIVE Contract
#
# 边界
# Candidate 只作为审阅输入；任何 LLM 输出都不能直接激活版本或决定安全结论。
#
# 调用链
# ContractWorkbench → ContractGovernance → Contract domain / StorageUnitOfWork
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import uuid4

from product.backend.core.contracts.analysis.assessment import assess_contract
from product.backend.core.contracts.lifecycle import revise_contract_version, transition_contract_version
from product.backend.core.contracts.models import (
    CandidateSuggestion,
    ContractAuditAction,
    ContractAuditEntry,
    ContractCandidate,
    ContractProvenance,
    ContractSourceType,
    ContractVersion,
    Requirement,
    SourceReference,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.lifecycle import ContractStatus
from product.backend.core.verification.permissions import PermissionContract
from product.backend.infra.storage import StorageUnitOfWork


class ContractGovernance:
    """维护需求、候选和唯一 PermissionContract 版本链。"""

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

    def create_requirement(self, project_id: str, *, source: SourceReference, text: str, security_tags: tuple[str, ...] = (), actor: str) -> Requirement:
        requirement = Requirement(
            requirement_id=f"req_{uuid4().hex}", project_id=project_id, source=source,
            text=text, security_tags=security_tags, created_by=actor, created_at_us=self._clock_us(),
        )
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            work.requirements.add(requirement)
            work.commit()
        return requirement

    def create_candidate(self, project_id: str, *, source: SourceReference, suggestion: CandidateSuggestion, requirement_ids: tuple[str, ...] = (), actor: str) -> ContractCandidate:
        candidate = ContractCandidate(
            candidate_id=f"cand_{uuid4().hex}", project_id=project_id, source=source,
            suggestion=suggestion, requirement_ids=requirement_ids,
            created_by=actor, created_at_us=self._clock_us(),
        )
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            self._validate_provenance(work, project_id, requirement_ids, ())
            work.contract_candidates.add(candidate)
            work.commit()
        return candidate

    def create_draft(self, project_id: str, contract_id: str, *, snapshot: PermissionContract, sources: tuple[SourceReference, ...] = (), requirement_ids: tuple[str, ...] = (), candidate_ids: tuple[str, ...] = (), actor: str) -> ContractVersion:
        """校验完整 provenance 后创建版本链中的首个 DRAFT。"""

        now_us = self._clock_us()
        if snapshot.contract_id != contract_id or snapshot.version != 1:
            raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "初稿必须使用 contract_id 一致且 version=1 的完整契约")
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            if work.contract_versions.list_for_contract(project_id, contract_id):
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "契约已经存在")
            provenance = self._provenance(work, project_id, sources, requirement_ids, candidate_ids)
            draft = ContractVersion(
                project_id=project_id, contract_id=contract_id, version=1,
                status=ContractStatus.DRAFT, snapshot=snapshot, provenance=provenance,
                audit=(ContractAuditEntry(action=ContractAuditAction.CREATED, actor=actor, occurred_at_us=now_us),),
                created_at_us=now_us, updated_at_us=now_us,
            )
            work.contract_versions.add(draft)
            work.commit()
        return draft

    def revise_active(self, project_id: str, contract_id: str, *, snapshot: PermissionContract, sources: tuple[SourceReference, ...] = (), requirement_ids: tuple[str, ...] = (), candidate_ids: tuple[str, ...] = (), actor: str) -> ContractVersion:
        """从当前 ACTIVE 版本派生新 DRAFT；旧版本保持不可变。"""

        now_us = self._clock_us()
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            active = work.contract_versions.get_active(project_id, contract_id)
            if active is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "没有可修订的 ACTIVE 契约")
            if snapshot.contract_id != contract_id or snapshot.version != active.version + 1:
                raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "修订必须显式提供下一版本完整契约")
            provenance = self._provenance(work, project_id, sources, requirement_ids, candidate_ids)
            revision = revise_contract_version(active, snapshot=snapshot, provenance=provenance, actor=actor, occurred_at_us=now_us)
            work.contract_versions.add(revision)
            work.commit()
        return revision

    def submit_review(self, project_id: str, contract_id: str, version: int, *, actor: str) -> ContractVersion:
        return self._transition(project_id, contract_id, version, ContractStatus.REVIEW, actor)

    def reject_review(self, project_id: str, contract_id: str, version: int, *, actor: str) -> ContractVersion:
        return self._transition(project_id, contract_id, version, ContractStatus.REJECTED, actor)

    def activate_review(self, project_id: str, contract_id: str, version: int, *, actor: str) -> ContractVersion:
        now_us = self._clock_us()
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            reviewed = work.contract_versions.get(project_id, contract_id, version)
            if reviewed is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
            self._ensure_review_assessment(work, reviewed)
            active = work.contract_versions.get_active(project_id, contract_id)
            activated = transition_contract_version(reviewed, ContractStatus.ACTIVE, actor=actor, occurred_at_us=now_us)
            if active is not None:
                work.contract_versions.replace(transition_contract_version(active, ContractStatus.SUPERSEDED, actor=actor, occurred_at_us=now_us))
            work.contract_versions.replace(activated)
            project = work.projects.get(project_id)
            if project is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            work.projects.replace(project.model_copy(update={"governed_contract_id": activated.contract_id, "governed_contract_version": activated.version, "updated_at_us": max(project.updated_at_us, now_us)}))
            work.commit()
        return activated

    def list_versions(self, project_id: str, contract_id: str) -> tuple[ContractVersion, ...]:
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            return work.contract_versions.list_for_contract(project_id, contract_id)

    def _transition(self, project_id: str, contract_id: str, version: int, target: ContractStatus, actor: str) -> ContractVersion:
        """在同一事务中校验评估、转换状态并追加审计记录。"""

        with self._uow_factory() as work:
            self._require_project(work, project_id)
            current = work.contract_versions.get(project_id, contract_id, version)
            if current is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
            if target is ContractStatus.REVIEW:
                self._ensure_review_assessment(work, current)
            updated = transition_contract_version(current, target, actor=actor, occurred_at_us=self._clock_us())
            work.contract_versions.replace(updated)
            work.commit()
        return updated

    def _ensure_review_assessment(self, work: StorageUnitOfWork, contract: ContractVersion) -> None:
        candidates = tuple(
            candidate for candidate_id in contract.provenance.candidate_ids
            if (candidate := work.contract_candidates.get(candidate_id)) is not None
        )
        if len(candidates) != len(contract.provenance.candidate_ids):
            raise JiejianError(ErrorCode.CONTRACT_ASSESSMENT_BLOCKED, "契约引用的候选不存在")
        assessment = assess_contract(
            contract,
            candidates=candidates,
            available_observations=self._available_observations or ("resource_state",),
        )
        if not assessment.eligible:
            raise JiejianError(ErrorCode.CONTRACT_ASSESSMENT_BLOCKED, "契约未通过确定性审阅评估")

    @staticmethod
    def _require_project(work: StorageUnitOfWork, project_id: str) -> None:
        if work.projects.get(project_id) is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")

    @staticmethod
    def _validate_provenance(work, project_id: str, requirement_ids: tuple[str, ...], candidate_ids: tuple[str, ...]) -> None:
        for requirement_id in requirement_ids:
            requirement = work.requirements.get(requirement_id)
            if requirement is None or requirement.project_id != project_id:
                raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "契约引用了不存在或跨项目的需求")
        for candidate_id in candidate_ids:
            candidate = work.contract_candidates.get(candidate_id)
            if candidate is None or candidate.project_id != project_id:
                raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "契约引用了不存在或跨项目的候选")

    @classmethod
    def _provenance(cls, work, project_id, sources, requirement_ids, candidate_ids) -> ContractProvenance:
        cls._validate_provenance(work, project_id, requirement_ids, candidate_ids)
        referenced_sources = list(sources)
        referenced_sources.extend(
            requirement.source
            for requirement_id in requirement_ids
            if (requirement := work.requirements.get(requirement_id)) is not None
        )
        referenced_sources.extend(
            candidate.source
            for candidate_id in candidate_ids
            if (candidate := work.contract_candidates.get(candidate_id)) is not None
        )
        resolved_sources = tuple(
            sorted(
                set(referenced_sources),
                key=lambda item: (item.source_type.value, item.locator, item.content_sha256),
            )
        )
        return ContractProvenance(
            requirement_ids=requirement_ids,
            candidate_ids=candidate_ids,
            sources=resolved_sources,
        )
