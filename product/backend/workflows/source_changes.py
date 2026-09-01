# =============================================================================
# 代码变化事实与权限实现影响服务
#
# 定位
#   Agent 声明完成变更后，受控源码重分析与长期 PermissionIntent 之间的确定性编排层。
#
# 职责
#   校验可选修复引用｜保存有界声明｜生成权威文件 diff｜评估逐 Intent 影响｜形成唯一重验 inspection。
#
# 边界
#   不信任 claimed paths，不复制 RepairContract，不读取 Git 或源码正文，不调用 LLM/Runner，也不修改权限真源。
#
# 调用链
#   ApplicationCore → SourceChangeService → ApplicationUnderstanding / PermissionIntent / Storage
# =============================================================================

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from product.backend.core.application_understanding import (
    ActionCandidate,
    ApplicationUnderstanding,
    CandidateEvidence,
    RoleCandidate,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import (
    IntentImplementationBinding,
    IntentImplementationBindingStatus,
    PermissionIntentEffectiveState,
    PermissionIntentRevision,
)
from product.backend.core.repair import RepairContractReference
from product.backend.core.source_changes import (
    ChangeImpactAssessment,
    ChangeManifest,
    IntentChangeImpact,
    RevalidationPlan,
    SourceChangeSet,
    SourceRevisionSnapshot,
    change_impact_fingerprint,
    normalize_relative_source_path,
    source_change_fingerprint,
)
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.workflows.application_understanding.service import (
    ApplicationUnderstandingService,
)
from product.backend.workflows.permission_intents import PermissionIntentService
from product.backend.workflows.results.repair import RepairContractService


class SourceChangeView(BaseModel):
    """给 GUI 与 MCP 的有界变化摘要；只暴露授权源码根下的相对路径。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    change_id: str = Field(pattern=r"^chg_[0-9a-f]{32}$")
    project_id: str
    reason: str
    submitted_by: str = Field(min_length=1, max_length=128)
    created_at_us: int = Field(ge=0)
    status: Literal["COMPARABLE", "NO_BASELINE"]
    complete: bool
    actual_changed_path_count: int = Field(ge=0)
    added_count: int = Field(ge=0)
    modified_count: int = Field(ge=0)
    removed_count: int = Field(ge=0)
    claimed_paths: tuple[str, ...] = Field(default=(), max_length=128)
    added_paths: tuple[str, ...] = Field(default=(), max_length=512)
    modified_paths: tuple[str, ...] = Field(default=(), max_length=512)
    removed_paths: tuple[str, ...] = Field(default=(), max_length=512)
    directly_affected_count: int = Field(ge=0)
    mapping_review_required_count: int = Field(ge=0)
    no_direct_evidence_count: int = Field(ge=0)
    review_intent_ids: tuple[str, ...] = Field(default=(), max_length=1024)
    summary: str = Field(min_length=1, max_length=240)
    next_path: Literal["/permissions"] | None = None

    @field_validator(
        "claimed_paths",
        "added_paths",
        "modified_paths",
        "removed_paths",
    )
    @classmethod
    def validate_relative_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """产品投影复用源码授权边界，不接受绝对路径或父目录跳转。"""

        return tuple(normalize_relative_source_path(value) for value in values)


class SourceRevalidationInspectionStatus(StrEnum):
    READY = "READY"
    NO_BASELINE = "NO_BASELINE"
    SOURCE_STALE = "SOURCE_STALE"
    POLICY_STALE = "POLICY_STALE"
    MAPPING_REVIEW_REQUIRED = "MAPPING_REVIEW_REQUIRED"


class SourceWorkspaceInspectionStatus(StrEnum):
    CURRENT = "CURRENT"
    DRIFTED = "DRIFTED"
    UNAVAILABLE = "UNAVAILABLE"


class SourceWorkspaceInspection(BaseModel):
    """源码工作区与已登记应用理解身份的只读比较。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    project_id: str
    status: SourceWorkspaceInspectionStatus
    registered_source_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    live_source_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)


class SourceRevalidationInspection(BaseModel):
    """一次变化相对当前源码、权限版本和实现映射的唯一只读判定。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )

    project_id: str
    change_id: str = Field(pattern=r"^chg_[0-9a-f]{32}$")
    status: SourceRevalidationInspectionStatus
    reason_codes: tuple[str, ...] = Field(default=(), max_length=32)
    impact_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_intent_ids: tuple[str, ...] = Field(default=(), max_length=4096)
    review_intent_ids: tuple[str, ...] = Field(default=(), max_length=4096)
    repair_reference: RepairContractReference | None = None


class SourceChangeService:
    """claimed paths 只作为展示线索，实际变化和权限影响始终由服务端形成。"""

    def __init__(
        self,
        uow_factory: Callable[..., StorageUnitOfWork],
        *,
        application_understanding: ApplicationUnderstandingService,
        permission_intents: PermissionIntentService,
        repair_contracts: RepairContractService | None = None,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._application_understanding = application_understanding
        self._permission_intents = permission_intents
        self._repair_contracts = repair_contracts
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)

    def submit(
        self,
        project_id: str,
        *,
        reason: str,
        claimed_paths: Iterable[str] = (),
        submitted_by: str,
        repair_reference: RepairContractReference | None = None,
    ) -> tuple[ChangeManifest, SourceChangeSet, ChangeImpactAssessment]:
        """按旧快照、重分析、新快照、真实 diff、绑定刷新和影响评估的顺序执行。"""

        if repair_reference is not None:
            if self._repair_contracts is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, "修复要求服务未装配")
            self._repair_contracts.verify_reference(project_id, repair_reference)
        now_us = self._clock_us()
        normalized_claims = tuple(
            sorted(
                (normalize_relative_source_path(path) for path in claimed_paths),
                key=lambda item: (item.casefold(), item),
            )
        )
        manifest = ChangeManifest(
            change_id=f"chg_{uuid.uuid4().hex}",
            project_id=project_id,
            reason=reason,
            claimed_paths=normalized_claims,
            repair_reference=repair_reference,
            submitted_by=submitted_by,
            created_at_us=now_us,
        )
        with self._uow_factory() as work:
            understanding = work.application_understanding.get(project_id)
            baseline = (
                None
                if understanding is None or understanding.source_fingerprint is None
                else work.source_changes.snapshot_for_fingerprint(
                    project_id,
                    understanding.source_fingerprint,
                )
            )
            oracle_before = self._oracle_state(work, project_id)
        if understanding is None:
            raise JiejianError(
                ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND,
                "当前项目还没有应用连接记录",
            )

        updated = self._application_understanding.analyze_source_for_change(
            project_id,
            revision=understanding.revision,
        )
        with self._uow_factory() as work:
            current = work.source_changes.snapshot_for_fingerprint(
                project_id,
                str(updated.source_fingerprint),
            )
        if current is None:
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "源码重分析未形成版本快照")
        change_set = self._build_change_set(manifest, baseline, current)

        self._permission_intents.refresh_bindings(project_id)
        with self._uow_factory() as work:
            assessment = self._assess(
                work,
                manifest,
                change_set,
                updated,
            )
            oracle_after = self._oracle_state(work, project_id)
            if oracle_after != oracle_before:
                raise JiejianError(
                    ErrorCode.STORAGE_FAILURE,
                    "代码变化分析不得修改权限意图或策略版本",
                )
            work.source_changes.add_change(manifest, change_set, assessment)
            work.commit()
        return manifest, change_set, assessment

    def get(
        self,
        change_id: str,
    ) -> tuple[ChangeManifest, SourceChangeSet, ChangeImpactAssessment]:
        with self._uow_factory() as work:
            manifest = work.source_changes.manifest(change_id)
            change_set = work.source_changes.change_set(change_id)
            assessment = work.source_changes.assessment(change_id)
        if manifest is None or change_set is None or assessment is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "代码变化记录不存在")
        return manifest, change_set, assessment

    def latest(
        self,
        project_id: str,
    ) -> tuple[ChangeManifest, SourceChangeSet, ChangeImpactAssessment] | None:
        with self._uow_factory() as work:
            assessment = work.source_changes.latest_assessment(project_id)
            if assessment is None:
                return None
            manifest = work.source_changes.manifest(assessment.change_id)
            change_set = work.source_changes.change_set(assessment.change_id)
        if manifest is None or change_set is None:
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "代码变化聚合数据不完整")
        return manifest, change_set, assessment

    def latest_for_repair(
        self,
        project_id: str,
        reference: RepairContractReference,
    ) -> tuple[ChangeManifest, SourceChangeSet, ChangeImpactAssessment] | None:
        """读取项目内最近一条精确关联修复要求的完整变化聚合。"""

        if self._repair_contracts is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "修复要求服务未装配")
        self._repair_contracts.verify_reference(project_id, reference)
        with self._uow_factory() as work:
            manifest = work.source_changes.latest_manifest_for_repair(project_id, reference)
            if manifest is None:
                return None
            change_set = work.source_changes.change_set(manifest.change_id)
            assessment = work.source_changes.assessment(manifest.change_id)
        if change_set is None or assessment is None:
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "代码变化聚合数据不完整")
        return manifest, change_set, assessment

    def inspect_workspace(self, project_id: str) -> SourceWorkspaceInspection:
        """用正式源码分析器比较 live 与登记 fingerprint，全程零写入。"""

        try:
            understanding = self._application_understanding.get(project_id)
        except JiejianError as exc:
            return SourceWorkspaceInspection(
                project_id=project_id,
                status=SourceWorkspaceInspectionStatus.UNAVAILABLE,
                reason_codes=(exc.code,),
            )
        registered = understanding.source_fingerprint
        if registered is None:
            return SourceWorkspaceInspection(
                project_id=project_id,
                status=SourceWorkspaceInspectionStatus.UNAVAILABLE,
                reason_codes=("SOURCE_BASELINE_MISSING",),
            )
        try:
            live = self._application_understanding.inspect_source_fingerprint(project_id)
        except JiejianError as exc:
            return SourceWorkspaceInspection(
                project_id=project_id,
                status=SourceWorkspaceInspectionStatus.UNAVAILABLE,
                registered_source_fingerprint=registered,
                reason_codes=(exc.code,),
            )
        drifted = live != registered
        return SourceWorkspaceInspection(
            project_id=project_id,
            status=(
                SourceWorkspaceInspectionStatus.DRIFTED
                if drifted
                else SourceWorkspaceInspectionStatus.CURRENT
            ),
            registered_source_fingerprint=registered,
            live_source_fingerprint=live,
            reason_codes=("SOURCE_WORKSPACE_DRIFTED",) if drifted else (),
        )

    def view(self, change_id: str) -> SourceChangeView:
        """读取单次变化的最小产品摘要。"""

        return self._view(self.get(change_id))

    def latest_view(self, project_id: str) -> SourceChangeView | None:
        """读取项目最近一次变化摘要；没有记录时返回空。"""

        latest = self.latest(project_id)
        return None if latest is None else self._view(latest)

    def list_views(
        self,
        project_id: str,
        *,
        limit: int = 50,
    ) -> tuple[SourceChangeView, ...]:
        """读取有界变化时间线；只返回产品摘要，不暴露源码正文或内部指纹。"""

        bounded_limit = max(1, min(limit, 100))
        with self._uow_factory() as work:
            assessments = work.source_changes.list_assessments(
                project_id,
                limit=bounded_limit,
            )
            aggregates = tuple(
                (
                    work.source_changes.manifest(assessment.change_id),
                    work.source_changes.change_set(assessment.change_id),
                    assessment,
                )
                for assessment in assessments
            )
        if any(
            manifest is None or change_set is None
            for manifest, change_set, _ in aggregates
        ):
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "代码变化聚合数据不完整")
        return tuple(
            self._view((manifest, change_set, assessment))
            for manifest, change_set, assessment in aggregates
            if manifest is not None and change_set is not None
        )

    def inspect_revalidation(
        self,
        project_id: str,
        change_id: str,
    ) -> SourceRevalidationInspection:
        """只读核对变化是否仍匹配当前源码、权限版本和 Human-approved binding。"""

        with self._uow_factory() as work:
            manifest = work.source_changes.manifest(change_id)
            change_set = work.source_changes.change_set(change_id)
            assessment = work.source_changes.assessment(change_id)
            understanding = work.application_understanding.get(project_id)
            latest = tuple(
                item
                for item in work.permission_intents.list_latest(project_id)
                if item.effective_state is PermissionIntentEffectiveState.ACTIVE
            )
            bindings = {
                (item.intent_id, item.intent_revision): item
                for item in work.permission_intents.list_bindings(project_id)
            }
            current_snapshot = (
                None
                if change_set is None
                else work.source_changes.snapshot(change_set.current_snapshot_id)
            )
        if manifest is None or change_set is None or assessment is None:
            raise JiejianError(ErrorCode.STATE_PRECONDITION, "代码变化记录不存在")
        if manifest.project_id != project_id:
            raise JiejianError(ErrorCode.PROJECT_NOT_FOUND, "代码变化不属于当前应用")
        if current_snapshot is None or understanding is None:
            raise JiejianError(ErrorCode.STORAGE_FAILURE, "代码变化缺少可验证的源码版本")
        if not assessment.complete:
            return SourceRevalidationInspection(
                project_id=project_id,
                change_id=change_id,
                status=SourceRevalidationInspectionStatus.NO_BASELINE,
                reason_codes=assessment.reason_codes,
                impact_fingerprint=assessment.impact_fingerprint,
                source_fingerprint=current_snapshot.source_fingerprint,
                repair_reference=manifest.repair_reference,
            )
        if understanding.source_fingerprint != current_snapshot.source_fingerprint:
            return SourceRevalidationInspection(
                project_id=project_id,
                change_id=change_id,
                status=SourceRevalidationInspectionStatus.SOURCE_STALE,
                reason_codes=("SOURCE_FINGERPRINT_STALE",),
                impact_fingerprint=assessment.impact_fingerprint,
                source_fingerprint=current_snapshot.source_fingerprint,
                repair_reference=manifest.repair_reference,
            )

        revisions = {item.intent_id: item for item in latest}
        impacts = {item.intent_id: item for item in assessment.impacts}
        policy_drift = set(revisions) != set(impacts) or any(
            impacts[item.intent_id].intent_revision != item.revision
            or impacts[item.intent_id].intent_hash != item.intent_hash
            for item in latest
            if item.intent_id in impacts
        )
        if policy_drift:
            return SourceRevalidationInspection(
                project_id=project_id,
                change_id=change_id,
                status=SourceRevalidationInspectionStatus.POLICY_STALE,
                reason_codes=("PERMISSION_POLICY_STALE",),
                impact_fingerprint=assessment.impact_fingerprint,
                source_fingerprint=current_snapshot.source_fingerprint,
                repair_reference=manifest.repair_reference,
            )

        mapping_review: list[str] = []
        required: list[str] = []
        for intent_id, revision in sorted(revisions.items()):
            binding = bindings.get((intent_id, revision.revision))
            impact = impacts[intent_id]
            if binding is None or binding.status is not IntentImplementationBindingStatus.CURRENT:
                mapping_review.append(intent_id)
                continue
            if (
                impact.classification == "MAPPING_REVIEW_REQUIRED"
                and impact.binding_updated_at_us is not None
                and binding.updated_at_us <= impact.binding_updated_at_us
            ):
                # CURRENT 只描述当前映射可用；标记未前进说明它没有在本次评估后经 Human Approval 重绑。
                mapping_review.append(intent_id)
                continue
            if impact.classification in {
                "DIRECTLY_AFFECTED",
                "MAPPING_REVIEW_REQUIRED",
            }:
                # 人工重绑完成后仍保守重验原先需要复核的权限，不把旧评估改写成安全结论。
                required.append(intent_id)
        status = (
            SourceRevalidationInspectionStatus.MAPPING_REVIEW_REQUIRED
            if mapping_review
            else SourceRevalidationInspectionStatus.READY
        )
        return SourceRevalidationInspection(
            project_id=project_id,
            change_id=change_id,
            status=status,
            reason_codes=("MAPPING_REVIEW_REQUIRED",) if mapping_review else (),
            impact_fingerprint=assessment.impact_fingerprint,
            source_fingerprint=current_snapshot.source_fingerprint,
            required_intent_ids=tuple(required),
            review_intent_ids=tuple(mapping_review),
            repair_reference=manifest.repair_reference,
        )

    def revalidation_plan(self, project_id: str, change_id: str) -> RevalidationPlan:
        """只把 READY inspection 转成执行计划，其余状态沿用既有 fail-closed 错误。"""

        inspection = self.inspect_revalidation(project_id, change_id)
        if inspection.status is SourceRevalidationInspectionStatus.NO_BASELINE:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "当前代码变化没有可比较基线，请重新提交变化说明",
                details={
                    "change_id": change_id,
                    "reason_codes": inspection.reason_codes,
                },
            )
        if inspection.status is SourceRevalidationInspectionStatus.SOURCE_STALE:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "源码已经发生后续变化，请重新提交变化说明",
                details={"change_id": change_id},
            )
        if inspection.status is SourceRevalidationInspectionStatus.POLICY_STALE:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "权限要求已经变化，请基于当前权限版本重新提交代码变化",
                details={"change_id": change_id, "next_path": "/permissions"},
            )
        if inspection.status is SourceRevalidationInspectionStatus.MAPPING_REVIEW_REQUIRED:
            raise JiejianError(
                ErrorCode.STATE_PRECONDITION,
                "代码变化涉及的实现映射需要先由用户确认",
                details={
                    "change_id": change_id,
                    "next_path": "/permissions",
                    "intent_ids": inspection.review_intent_ids,
                },
            )
        return RevalidationPlan(
            change_id=change_id,
            project_id=project_id,
            impact_fingerprint=inspection.impact_fingerprint,
            required_intent_ids=inspection.required_intent_ids,
            source_fingerprint=inspection.source_fingerprint,
            repair_reference=inspection.repair_reference,
        )

    @staticmethod
    def _view(
        aggregate: tuple[ChangeManifest, SourceChangeSet, ChangeImpactAssessment],
    ) -> SourceChangeView:
        manifest, change_set, assessment = aggregate
        directly_affected = tuple(
            item
            for item in assessment.impacts
            if item.classification == "DIRECTLY_AFFECTED"
        )
        mapping_review = tuple(
            item
            for item in assessment.impacts
            if item.classification == "MAPPING_REVIEW_REQUIRED"
        )
        no_direct_evidence = tuple(
            item
            for item in assessment.impacts
            if item.classification == "NO_DIRECT_EVIDENCE"
        )
        if not assessment.complete:
            summary = "当前没有可比较的源码基线，需要先建立基线后再提交变化。"
        elif mapping_review:
            summary = (
                f"有 {len(mapping_review)} 条权限要求无法自动对应到修改后的代码，"
                "需要你确认。"
            )
        elif directly_affected:
            summary = f"发现 {len(directly_affected)} 条权限要求与本次变化直接相关。"
        else:
            summary = (
                "当前没有发现与已知权限实现直接相交的变化；"
                "这不代表其他未建模影响一定不存在。"
            )
        return SourceChangeView(
            change_id=manifest.change_id,
            project_id=manifest.project_id,
            reason=manifest.reason,
            submitted_by=manifest.submitted_by,
            created_at_us=manifest.created_at_us,
            status=change_set.status,
            complete=assessment.complete,
            actual_changed_path_count=len(change_set.changed_paths),
            added_count=len(change_set.added_paths),
            modified_count=len(change_set.modified_paths),
            removed_count=len(change_set.removed_paths),
            claimed_paths=manifest.claimed_paths,
            added_paths=change_set.added_paths,
            modified_paths=change_set.modified_paths,
            removed_paths=change_set.removed_paths,
            directly_affected_count=len(directly_affected),
            mapping_review_required_count=len(mapping_review),
            no_direct_evidence_count=len(no_direct_evidence),
            review_intent_ids=tuple(item.intent_id for item in mapping_review),
            summary=summary,
            next_path="/permissions" if mapping_review else None,
        )

    @staticmethod
    def _build_change_set(
        manifest: ChangeManifest,
        baseline: SourceRevisionSnapshot | None,
        current: SourceRevisionSnapshot,
    ) -> SourceChangeSet:
        if baseline is None:
            payload = {
                "change_id": manifest.change_id,
                "project_id": manifest.project_id,
                "previous_snapshot_id": None,
                "current_snapshot_id": current.snapshot_id,
                "status": "NO_BASELINE",
                "added_paths": (),
                "modified_paths": (),
                "removed_paths": (),
            }
        else:
            previous_files = {item.relative_path: item.content_sha256 for item in baseline.files}
            current_files = {item.relative_path: item.content_sha256 for item in current.files}
            added = sorted(
                current_files.keys() - previous_files.keys(),
                key=lambda item: (item.casefold(), item),
            )
            removed = sorted(
                previous_files.keys() - current_files.keys(),
                key=lambda item: (item.casefold(), item),
            )
            modified = sorted(
                (
                    path
                    for path in previous_files.keys() & current_files.keys()
                    if previous_files[path] != current_files[path]
                ),
                key=lambda item: (item.casefold(), item),
            )
            payload = {
                "change_id": manifest.change_id,
                "project_id": manifest.project_id,
                "previous_snapshot_id": baseline.snapshot_id,
                "current_snapshot_id": current.snapshot_id,
                "status": "COMPARABLE",
                "added_paths": tuple(added),
                "modified_paths": tuple(modified),
                "removed_paths": tuple(removed),
            }
        return SourceChangeSet(
            **payload,
            change_fingerprint=source_change_fingerprint(payload),
            created_at_us=manifest.created_at_us,
        )

    def _assess(
        self,
        work: StorageUnitOfWork,
        manifest: ChangeManifest,
        change_set: SourceChangeSet,
        understanding: ApplicationUnderstanding,
    ) -> ChangeImpactAssessment:
        latest = tuple(
            revision
            for revision in work.permission_intents.list_latest(manifest.project_id)
            if revision.effective_state is PermissionIntentEffectiveState.ACTIVE
        )
        bindings = {
            (binding.intent_id, binding.intent_revision): binding
            for binding in work.permission_intents.list_bindings(manifest.project_id)
        }
        actions = {candidate.candidate_id: candidate for candidate in understanding.action_candidates}
        roles = {candidate.candidate_id: candidate for candidate in understanding.role_candidates}
        complete = change_set.status == "COMPARABLE"
        impacts = tuple(
            self._intent_impact(
                revision,
                bindings.get((revision.intent_id, revision.revision)),
                actions,
                roles,
                change_set,
                complete=complete,
            )
            for revision in sorted(latest, key=lambda item: item.intent_id)
        )
        reason_codes = () if complete else ("NO_BASELINE",)
        fingerprint_payload = {
            "change_id": manifest.change_id,
            "project_id": manifest.project_id,
            "change_fingerprint": change_set.change_fingerprint,
            "complete": complete,
            "reason_codes": list(reason_codes),
            "impacts": [item.model_dump(mode="json") for item in impacts],
        }
        return ChangeImpactAssessment(
            change_id=manifest.change_id,
            project_id=manifest.project_id,
            change_fingerprint=change_set.change_fingerprint,
            complete=complete,
            reason_codes=reason_codes,
            impacts=impacts,
            impact_fingerprint=change_impact_fingerprint(fingerprint_payload),
            created_at_us=manifest.created_at_us,
        )

    @staticmethod
    def _intent_impact(
        revision: PermissionIntentRevision,
        binding: IntentImplementationBinding | None,
        actions: dict[str, ActionCandidate],
        roles: dict[str, RoleCandidate],
        change_set: SourceChangeSet,
        *,
        complete: bool,
    ) -> IntentChangeImpact:
        if binding is None:
            return SourceChangeService._mapping_review_impact(
                revision,
                ("BINDING_MISSING",),
                binding=None,
            )
        if binding.status is not IntentImplementationBindingStatus.CURRENT:
            return SourceChangeService._mapping_review_impact(
                revision,
                ("BINDING_NOT_CURRENT", *binding.reason_codes),
                binding=binding,
            )
        if not complete:
            return SourceChangeService._mapping_review_impact(
                revision,
                ("NO_BASELINE",),
                binding=binding,
            )

        changed = {path.casefold(): path for path in change_set.changed_paths}
        candidate_groups = (
            (actions.get(binding.action_candidate_id), "ACTION_EVIDENCE_CHANGED"),
            (roles.get(binding.subject_role_candidate_id), "SUBJECT_EVIDENCE_CHANGED"),
            (roles.get(binding.resource_owner_role_candidate_id), "OWNER_EVIDENCE_CHANGED"),
        )
        relevant: dict[str, str] = {}
        reasons: list[str] = []
        for candidate, reason in candidate_groups:
            if candidate is None or candidate.stale:
                return SourceChangeService._mapping_review_impact(
                    revision,
                    ("CANDIDATE_UNRESOLVED",),
                    binding=binding,
                )
            if not candidate.evidence:
                return SourceChangeService._mapping_review_impact(
                    revision,
                    ("IMPLEMENTATION_EVIDENCE_MISSING",),
                    binding=binding,
                )
            matched = SourceChangeService._matched_paths(candidate.evidence, changed)
            if matched:
                reasons.append(reason)
                relevant.update((path.casefold(), path) for path in matched)
        if relevant:
            return IntentChangeImpact(
                intent_id=revision.intent_id,
                intent_revision=revision.revision,
                intent_hash=revision.intent_hash,
                classification="DIRECTLY_AFFECTED",
                message="发现直接实现关联",
                relevant_paths=tuple(
                    sorted(relevant.values(), key=lambda item: (item.casefold(), item))
                ),
                reason_codes=tuple(dict.fromkeys(reasons)),
                binding_updated_at_us=binding.updated_at_us,
            )
        return IntentChangeImpact(
            intent_id=revision.intent_id,
            intent_revision=revision.revision,
            intent_hash=revision.intent_hash,
            classification="NO_DIRECT_EVIDENCE",
            message="当前没有发现直接实现关联",
            reason_codes=("NO_DIRECT_IMPLEMENTATION_EVIDENCE",),
            binding_updated_at_us=binding.updated_at_us,
        )

    @staticmethod
    def _mapping_review_impact(
        revision: PermissionIntentRevision,
        reasons: tuple[str, ...],
        *,
        binding: IntentImplementationBinding | None,
    ) -> IntentChangeImpact:
        return IntentChangeImpact(
            intent_id=revision.intent_id,
            intent_revision=revision.revision,
            intent_hash=revision.intent_hash,
            classification="MAPPING_REVIEW_REQUIRED",
            message="实现映射需要人工复核",
            reason_codes=tuple(dict.fromkeys(reasons)),
            binding_updated_at_us=None if binding is None else binding.updated_at_us,
        )

    @staticmethod
    def _matched_paths(
        evidence: tuple[CandidateEvidence, ...],
        changed: dict[str, str],
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    changed[item.relative_path.casefold()]
                    for item in evidence
                    if item.relative_path.casefold() in changed
                },
                key=lambda item: (item.casefold(), item),
            )
        )

    @staticmethod
    def _oracle_state(
        work: StorageUnitOfWork,
        project_id: str,
    ) -> tuple[int, tuple[tuple[str, int, str, int], ...]]:
        state = work.permission_intents.policy_state(project_id)
        latest = work.permission_intents.list_latest(project_id)
        return (
            0 if state is None else state.policy_epoch,
            tuple(
                sorted(
                    (
                        item.intent_id,
                        item.revision,
                        item.intent_hash,
                        item.policy_epoch,
                    )
                    for item in latest
                )
            ),
        )


__all__ = [
    "SourceChangeService",
    "SourceChangeView",
    "SourceRevalidationInspection",
    "SourceRevalidationInspectionStatus",
    "SourceWorkspaceInspection",
    "SourceWorkspaceInspectionStatus",
]
