# =============================================================================
# Contract 工作台
#
# 定位
#   CLI、API 与 GUI 共享的 Contract 建约、审阅、绑定应用门面
#
# 职责
#   编排候选生成｜聚合治理与分析视图｜绑定项目 ACTIVE Contract
#
# 调用链
#   CLI / API → ContractWorkbenchService → Governance / Analysis / LLM / Projects
# =============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .analysis.models import (
    AnalysisSeverity,
    CandidateBatch,
    CandidateMergeResult,
    ContractReviewAssessment,
    ContractVersionDiff,
)
from .analysis.canonical import canonical_sha256
from .models import (
    ContractCandidate,
    ContractSourceType,
    ContractVersion,
    Requirement,
    SourceReference,
)
from .analysis.drift import DriftReport
from ..domain.lifecycle import ContractStatus
from ..errors import ErrorCode, JiejianError
from ..storage import ProjectRecord, StorageUnitOfWork
from .analysis.service import ContractAnalysisService, ContractHistoryResolution
from .governance_service import ContractGovernanceService
from .llm.service import LLMCandidateGenerationService
from .llm.models import LLMGenerationResult
from ..projects.service import ProjectControlService


class WorkbenchModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    schema_version: Literal["1"] = "1"


class CandidateDerivationResult(WorkbenchModel):
    batches: tuple[CandidateBatch, ...]
    merge: CandidateMergeResult
    persisted_candidates: tuple[ContractCandidate, ...] = ()


class ContractWorkbenchSnapshot(WorkbenchModel):
    project: ProjectRecord
    requirements: tuple[Requirement, ...]
    candidates: tuple[ContractCandidate, ...]
    versions: tuple[ContractVersion, ...]
    flow_batch: CandidateBatch
    flow_merge: CandidateMergeResult
    llm_available: bool


class ContractWorkbenchService:
    """把已有治理、分析、LLM 和项目控制服务组合为工作台接口。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        projects: ProjectControlService,
        governance: ContractGovernanceService,
        analysis: ContractAnalysisService,
        llm_candidates: LLMCandidateGenerationService,
    ) -> None:
        self._uow_factory = uow_factory
        self._projects = projects
        self._governance = governance
        self._analysis = analysis
        self._llm = llm_candidates

    def snapshot(self, project_id: str) -> ContractWorkbenchSnapshot:
        record, bundle = self._projects.current_bundle(project_id)
        flow_batch = self._analysis.from_flow(project_id, bundle.flow)
        flow_merge = self._analysis.merge(flow_batch.candidates)
        with self._uow_factory() as work:
            requirements = work.requirements.list_for_project(project_id)
            candidates = work.contract_candidates.list_for_project(project_id)
            versions = work.contract_versions.list_for_project(project_id)
        return ContractWorkbenchSnapshot(
            project=record,
            requirements=requirements,
            candidates=candidates,
            versions=versions,
            flow_batch=flow_batch,
            flow_merge=flow_merge,
            llm_available=self._llm.available,
        )

    def create_requirement(
        self,
        project_id: str,
        *,
        text: str,
        security_tags: tuple[str, ...],
        actor: str,
    ) -> Requirement:
        normalized_text = text.strip()
        normalized_tags = tuple(sorted({tag.strip() for tag in security_tags}))
        content_hash = canonical_sha256(
            {"text": normalized_text, "security_tags": normalized_tags}
        )
        return self._governance.create_requirement(
            project_id,
            source=SourceReference(
                source_type=ContractSourceType.REQUIREMENT_TEXT,
                locator=f"api:requirement:{content_hash}",
                content_sha256=content_hash,
            ),
            text=normalized_text,
            security_tags=normalized_tags,
            actor=actor,
        )

    def derive_candidates(
        self,
        project_id: str,
        *,
        requirement_ids: tuple[str, ...],
        include_flow: bool,
        actor: str,
    ) -> CandidateDerivationResult:
        if len(set(requirement_ids)) != len(requirement_ids):
            raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "需求选择重复")
        if not requirement_ids and not include_flow:
            raise JiejianError(ErrorCode.INPUT_INVALID, "未选择需求或 Flow")
        _, bundle = self._projects.current_bundle(project_id)
        with self._uow_factory() as work:
            requirements = tuple(work.requirements.get(item) for item in requirement_ids)
        if any(item is None or item.project_id != project_id for item in requirements):
            raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "需求不存在或跨项目")
        batches = [self._analysis.parse_requirement(item) for item in requirements if item is not None]
        if include_flow:
            batches.append(self._analysis.from_flow(project_id, bundle.flow))
        all_candidates = tuple(item for batch in batches for item in batch.candidates)
        merge = self._analysis.merge(all_candidates)
        if any(
            issue.severity is AnalysisSeverity.BLOCKING
            for batch in batches
            for issue in batch.issues
        ) or any(issue.severity is AnalysisSeverity.BLOCKING for issue in merge.issues):
            return CandidateDerivationResult(
                batches=tuple(batches),
                merge=merge,
                persisted_candidates=(),
            )
        persisted = self._persist_deterministic_candidates(project_id, all_candidates, actor)
        return CandidateDerivationResult(
            batches=tuple(batches),
            merge=merge,
            persisted_candidates=persisted,
        )

    def create_draft(
        self,
        project_id: str,
        contract_id: str,
        *,
        candidate_ids: tuple[str, ...],
        actor: str,
    ) -> ContractVersion:
        return self._governance.create_draft(
            project_id,
            contract_id,
            candidate_ids=candidate_ids,
            actor=actor,
        )

    def revise_active(
        self,
        project_id: str,
        contract_id: str,
        *,
        candidate_ids: tuple[str, ...],
        actor: str,
    ) -> ContractVersion:
        return self._governance.revise_active(
            project_id,
            contract_id,
            candidate_ids=candidate_ids,
            actor=actor,
        )

    def generate_llm(
        self,
        project_id: str,
        *,
        requirement_ids: tuple[str, ...],
        actor: str,
        profile_name: str | None = None,
    ) -> LLMGenerationResult:
        return self._llm.generate(
            project_id,
            requirement_ids,
            actor=actor,
            profile_name=profile_name,
        )

    def list_versions(self, project_id: str, contract_id: str) -> tuple[ContractVersion, ...]:
        return self._governance.list_versions(project_id, contract_id)

    def submit_review(self, project_id: str, contract_id: str, version: int, *, actor: str) -> ContractVersion:
        return self._governance.submit_review(project_id, contract_id, version, actor=actor)

    def reject_review(self, project_id: str, contract_id: str, version: int, *, actor: str) -> ContractVersion:
        return self._governance.reject_review(project_id, contract_id, version, actor=actor)

    def activate_review(self, project_id: str, contract_id: str, version: int, *, actor: str) -> ContractVersion:
        return self._governance.activate_review(project_id, contract_id, version, actor=actor)

    def assessment(self, project_id: str, contract_id: str, version: int) -> ContractReviewAssessment:
        return self._analysis.assess_stored_version(project_id, contract_id, version)

    def diff(self, project_id: str, contract_id: str, version: int, from_version: int) -> ContractVersionDiff:
        with self._uow_factory() as work:
            before = work.contract_versions.get(project_id, contract_id, from_version)
            after = work.contract_versions.get(project_id, contract_id, version)
        if before is None or after is None:
            raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
        return self._analysis.diff(before, after)

    def drift(self, project_id: str, contract_id: str, version: int) -> DriftReport:
        _, bundle = self._projects.current_bundle(project_id)
        with self._uow_factory() as work:
            contract = work.contract_versions.get(project_id, contract_id, version)
            requirements = work.requirements.list_for_project(project_id)
            candidates = work.contract_candidates.list_for_project(project_id)
        if contract is None:
            raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
        flow_batch = self._analysis.from_flow(project_id, bundle.flow)
        return self._analysis.drift(
            contract,
            requirements=requirements,
            requirement_candidates=tuple(
                item for item in candidates if item.source.source_type is not ContractSourceType.LLM
            ),
            llm_candidates=tuple(
                item for item in candidates if item.source.source_type is ContractSourceType.LLM
            ),
            available_rule_ids=tuple(item.rule.id for item in flow_batch.candidates),
            capability_candidates=flow_batch.candidates,
            available_observers=self._projects.current_observers(project_id),
        )

    def history(self, run_id: str) -> ContractHistoryResolution:
        return self._analysis.resolve_run_contract(run_id)

    def _persist_deterministic_candidates(
        self,
        project_id: str,
        candidates: tuple[ContractCandidate, ...],
        actor: str,
    ) -> tuple[ContractCandidate, ...]:
        resolved: list[ContractCandidate] = []
        pending: list[ContractCandidate] = []
        with self._uow_factory() as work:
            if work.projects.get(project_id) is None:
                raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")
            for candidate in candidates:
                if candidate.project_id != project_id:
                    raise JiejianError(ErrorCode.CONTRACT_REFERENCE_INVALID, "候选跨项目")
                existing = work.contract_candidates.get(candidate.candidate_id)
                if existing is not None:
                    if not _same_candidate_content(existing, candidate):
                        raise JiejianError(ErrorCode.CONTRACT_CANDIDATE_CONFLICT, "Candidate ID 内容冲突")
                    resolved.append(existing)
                    continue
                pending_candidate = candidate.model_copy(update={"created_by": actor})
                pending.append(pending_candidate)
                resolved.append(pending_candidate)
            for candidate in pending:
                work.contract_candidates.add(candidate)
            if pending:
                work.commit()
        return tuple(sorted(resolved, key=lambda item: item.candidate_id))


def _same_candidate_content(left: ContractCandidate, right: ContractCandidate) -> bool:
    return (
        left.project_id == right.project_id
        and left.source == right.source
        and left.rule == right.rule
        and left.requirement_ids == right.requirement_ids
        and left.llm_metadata == right.llm_metadata
    )
