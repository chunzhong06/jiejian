# =============================================================================
# Contract 治理应用服务
#
# 定位
#   Requirement、Candidate 与不可变 ContractVersion 之间的治理边界
#
# 职责
#   创建与修订版本｜执行状态转换门禁｜持久化来源和审阅证据
#
# 调用链
#   ContractWorkbench / CLI / API → ContractGovernanceService → Analysis / Storage
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import uuid4

from .analysis.assessment import assess_contract
from .analysis.merge import merge_candidates
from .analysis.sources.requirement import parse_requirement
from .governance import revise_contract_version, transition_contract_version
from .models import (
    ContractAuditAction,
    ContractAuditEntry,
    ContractCandidate,
    ContractProvenance,
    ContractVersion,
    Requirement,
    SourceReference,
)
from ..domain.lifecycle import ContractStatus
from ..verification.models import ContractRule, SecurityContract
from ..errors import ErrorCode, JiejianError
from ..storage import StorageUnitOfWork


class ContractGovernanceService:
    """维护不可信候选和人工审阅版本；不执行目标请求。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        clock_us: Callable[[], int] | None = None,
        available_observers: tuple[str, ...] | None = None,
        observer_resolver: Callable[[str], tuple[str, ...]] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
        self._available_observers = available_observers
        self._observer_resolver = observer_resolver

    def create_requirement(
        self,
        project_id: str,
        *,
        source: SourceReference,
        text: str,
        security_tags: tuple[str, ...] = (),
        actor: str,
    ) -> Requirement:
        requirement = Requirement(
            requirement_id=f"req_{uuid4().hex}",
            project_id=project_id,
            source=source,
            text=text,
            security_tags=security_tags,
            created_by=actor,
            created_at_us=self._clock_us(),
        )
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            work.requirements.add(requirement)
            work.commit()
        return requirement

    def create_candidate(
        self,
        project_id: str,
        *,
        source: SourceReference,
        rule: ContractRule,
        requirement_ids: tuple[str, ...] = (),
        actor: str,
    ) -> ContractCandidate:
        candidate = ContractCandidate(
            candidate_id=f"cand_{uuid4().hex}",
            project_id=project_id,
            source=source,
            rule=rule,
            requirement_ids=requirement_ids,
            created_by=actor,
            created_at_us=self._clock_us(),
        )
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            for requirement_id in requirement_ids:
                requirement = work.requirements.get(requirement_id)
                if requirement is None or requirement.project_id != project_id:
                    raise JiejianError(
                        ErrorCode.CONTRACT_REFERENCE_INVALID,
                        "候选引用了不存在或跨项目的需求",
                    )
            work.contract_candidates.add(candidate)
            work.commit()
        return candidate

    def create_draft(
        self,
        project_id: str,
        contract_id: str,
        *,
        rules: tuple[ContractRule, ...] = (),
        sources: tuple[SourceReference, ...] = (),
        requirement_ids: tuple[str, ...] = (),
        candidate_ids: tuple[str, ...] = (),
        actor: str,
    ) -> ContractVersion:
        now_us = self._clock_us()
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            if work.contract_versions.list_for_contract(project_id, contract_id):
                raise JiejianError(
                    ErrorCode.STATE_PRECONDITION,
                    "契约已经存在；ACTIVE 版本必须通过修订生成下一版本",
                )
            resolved_rules, provenance = self._resolve_material(
                work,
                project_id,
                rules=rules,
                sources=sources,
                requirement_ids=requirement_ids,
                candidate_ids=candidate_ids,
            )
            draft = ContractVersion(
                project_id=project_id,
                contract_id=contract_id,
                version=1,
                status=ContractStatus.DRAFT,
                snapshot=SecurityContract(
                    id=contract_id,
                    version=1,
                    status=ContractStatus.DRAFT,
                    rules=resolved_rules,
                ),
                provenance=provenance,
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

    def submit_review(
        self, project_id: str, contract_id: str, version: int, *, actor: str
    ) -> ContractVersion:
        return self._transition(
            project_id,
            contract_id,
            version,
            target=ContractStatus.REVIEW,
            actor=actor,
        )

    def reject_review(
        self, project_id: str, contract_id: str, version: int, *, actor: str
    ) -> ContractVersion:
        return self._transition(
            project_id,
            contract_id,
            version,
            target=ContractStatus.REJECTED,
            actor=actor,
        )

    def activate_review(
        self, project_id: str, contract_id: str, version: int, *, actor: str
    ) -> ContractVersion:
        now_us = self._clock_us()
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            project = work.projects.get(project_id)
            reviewed = work.contract_versions.get(project_id, contract_id, version)
            if reviewed is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
            self._ensure_review_assessment(work, reviewed)
            active = work.contract_versions.get_active(project_id, contract_id)
            activated = transition_contract_version(
                reviewed,
                ContractStatus.ACTIVE,
                actor=actor,
                occurred_at_us=now_us,
            )
            if active is not None:
                superseded = transition_contract_version(
                    active,
                    ContractStatus.SUPERSEDED,
                    actor=actor,
                    occurred_at_us=now_us,
                )
                work.contract_versions.replace(superseded)
            work.contract_versions.replace(activated)
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

    def revise_active(
        self,
        project_id: str,
        contract_id: str,
        *,
        rules: tuple[ContractRule, ...] | None = None,
        sources: tuple[SourceReference, ...] = (),
        requirement_ids: tuple[str, ...] = (),
        candidate_ids: tuple[str, ...] = (),
        actor: str,
    ) -> ContractVersion:
        now_us = self._clock_us()
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            active = work.contract_versions.get_active(project_id, contract_id)
            if active is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_ACTIVE, "没有可修订的 ACTIVE 契约")
            if rules is None and not sources and not requirement_ids and not candidate_ids:
                resolved_rules = active.snapshot.rules
                provenance = active.provenance
            else:
                resolved_rules, provenance = self._resolve_material(
                    work,
                    project_id,
                    rules=rules or (),
                    sources=sources,
                    requirement_ids=requirement_ids,
                    candidate_ids=candidate_ids,
                )
            revision = revise_contract_version(
                active,
                rules=resolved_rules,
                provenance=provenance,
                actor=actor,
                occurred_at_us=now_us,
            )
            work.contract_versions.add(revision)
            work.commit()
        return revision

    def list_versions(self, project_id: str, contract_id: str) -> tuple[ContractVersion, ...]:
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            return work.contract_versions.list_for_contract(project_id, contract_id)

    def _transition(
        self,
        project_id: str,
        contract_id: str,
        version: int,
        *,
        target: ContractStatus,
        actor: str,
    ) -> ContractVersion:
        with self._uow_factory() as work:
            self._require_project(work, project_id)
            current = work.contract_versions.get(project_id, contract_id, version)
            if current is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
            if target is ContractStatus.REVIEW:
                self._ensure_review_assessment(work, current)
            updated = transition_contract_version(
                current,
                target,
                actor=actor,
                occurred_at_us=self._clock_us(),
            )
            work.contract_versions.replace(updated)
            work.commit()
        return updated

    @staticmethod
    def _require_project(work: StorageUnitOfWork, project_id: str) -> None:
        if work.projects.get(project_id) is None:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "项目不存在")

    @staticmethod
    def _resolve_material(
        work: StorageUnitOfWork,
        project_id: str,
        *,
        rules: tuple[ContractRule, ...],
        sources: tuple[SourceReference, ...],
        requirement_ids: tuple[str, ...],
        candidate_ids: tuple[str, ...],
    ) -> tuple[tuple[ContractRule, ...], ContractProvenance]:
        if len({rule.id for rule in rules}) != len(rules):
            raise JiejianError(
                ErrorCode.CONTRACT_ASSESSMENT_BLOCKED,
                "契约规则 ID 重复",
            )
        resolved_requirements: list[Requirement] = []
        resolved_candidates: list[ContractCandidate] = []
        all_requirement_ids = list(requirement_ids)
        for candidate_id in candidate_ids:
            candidate = work.contract_candidates.get(candidate_id)
            if candidate is None or candidate.project_id != project_id:
                raise JiejianError(
                    ErrorCode.CONTRACT_REFERENCE_INVALID,
                    "契约引用了不存在或跨项目的候选",
                )
            resolved_candidates.append(candidate)
            all_requirement_ids.extend(candidate.requirement_ids)
        unique_requirement_ids = tuple(dict.fromkeys(all_requirement_ids))
        for requirement_id in unique_requirement_ids:
            requirement = work.requirements.get(requirement_id)
            if requirement is None or requirement.project_id != project_id:
                raise JiejianError(
                    ErrorCode.CONTRACT_REFERENCE_INVALID,
                    "契约引用了不存在或跨项目的需求",
                )
            resolved_requirements.append(requirement)
        merged = merge_candidates(tuple(resolved_candidates))
        if any(issue.severity.value == "BLOCKING" for issue in merged.issues):
            raise JiejianError(
                ErrorCode.CONTRACT_ASSESSMENT_BLOCKED,
                "候选冲突，不能形成契约草稿",
            )
        resolved_rules_list: list[ContractRule] = []
        by_rule_id: dict[str, ContractRule] = {}
        for rule in (*rules, *(item.rule for item in merged.candidates)):
            existing = by_rule_id.get(rule.id)
            if existing is not None and existing != rule:
                raise JiejianError(
                    ErrorCode.CONTRACT_ASSESSMENT_BLOCKED,
                    "同一规则 ID 的正文不一致",
                )
            if existing is None:
                by_rule_id[rule.id] = rule
                resolved_rules_list.append(rule)
        resolved_rules = tuple(resolved_rules_list)
        resolved_sources = tuple(
            sorted(
                dict.fromkeys(
                (
                    *sources,
                    *(requirement.source for requirement in resolved_requirements),
                    *(candidate.source for candidate in resolved_candidates),
                )
                ),
                key=lambda item: (item.source_type.value, item.locator, item.content_sha256),
            )
        )
        return resolved_rules, ContractProvenance(
            requirement_ids=unique_requirement_ids,
            candidate_ids=tuple(dict.fromkeys(candidate_ids)),
            sources=resolved_sources,
        )

    def _ensure_review_assessment(
        self,
        work: StorageUnitOfWork,
        contract: ContractVersion,
    ) -> None:
        candidates: list[ContractCandidate] = []
        referenced_candidates: list[ContractCandidate] = []
        for candidate_id in contract.provenance.candidate_ids:
            candidate = work.contract_candidates.get(candidate_id)
            if candidate is None or candidate.project_id != contract.project_id:
                raise JiejianError(
                    ErrorCode.CONTRACT_ASSESSMENT_BLOCKED,
                    "契约引用的候选不存在或跨项目",
                )
            referenced_candidates.append(candidate)
        source_issues = []
        has_llm_candidate = any(
            candidate.source.source_type.value == "llm"
            for candidate in referenced_candidates
        )
        for requirement_id in contract.provenance.requirement_ids:
            requirement = work.requirements.get(requirement_id)
            if requirement is None or requirement.project_id != contract.project_id:
                raise JiejianError(
                    ErrorCode.CONTRACT_ASSESSMENT_BLOCKED,
                    "契约引用的需求不存在或跨项目",
                )
            if has_llm_candidate and not any(
                requirement_id in candidate.requirement_ids
                for candidate in referenced_candidates
                if candidate.source.source_type.value != "llm"
            ):
                parsed = parse_requirement(requirement)
                candidates.extend(parsed.candidates)
                source_issues.extend(parsed.issues)
        candidates.extend(referenced_candidates)
        assessment = assess_contract(
            contract,
            candidates=tuple(candidates),
            source_issues=tuple(source_issues),
            available_observers=self._observers_for_project(contract.project_id),
        )
        if not assessment.eligible:
            raise JiejianError(
                ErrorCode.CONTRACT_ASSESSMENT_BLOCKED,
                "契约未通过确定性审阅评估",
                details={
                    "reason_codes": tuple(
                        issue.code.value for issue in assessment.blocking_issues
                    )
                },
            )

    def _observers_for_project(self, project_id: str) -> tuple[str, ...]:
        if self._observer_resolver is not None:
            return self._observer_resolver(project_id)
        return self._available_observers or ("http",)
