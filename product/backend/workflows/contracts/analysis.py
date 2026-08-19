# =============================================================================
# Contract 分析应用服务
#
# 定位
#   多来源候选、审阅评估、版本差异和 Drift 的只读分析边界
#
# 职责
#   调度确定性来源适配｜解析历史 Run 快照｜组合 Diff 与六类 Drift
#
# 边界
#   只读取治理与历史事实，不发起目标请求、不写 Contract 状态，也不接受 LLM 直接结论。
#
# 调用链
#   ContractWorkbench → ContractAnalysis → Sources / Assessment / Drift / Storage
# =============================================================================

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from product.backend.core.contracts.analysis.models import AnalysisIssue, CandidateBatch, CandidateMergeResult, ContractReviewAssessment, ContractVersionDiff
from product.backend.core.contracts.analysis.assessment import assess_contract
from product.backend.core.contracts.analysis.diff import diff_contract_versions
from product.backend.core.contracts.analysis.merge import merge_candidates
from product.backend.core.contracts.analysis.sources.fastapi_ast import parse_fastapi_source_candidates
from product.backend.workflows.contracts.flow_candidates import build_flow_candidates
from product.backend.core.contracts.analysis.sources.openapi import build_openapi_candidates
from product.backend.core.contracts.analysis.sources.requirement import parse_requirement
from product.backend.core.contracts.analysis.models import AnalysisReasonCode, AnalysisSeverity
from product.backend.core.contracts.models import ContractCandidate, ContractVersion, Requirement
from product.backend.core.contracts.analysis.drift import DriftReport, VerifiedBehaviorFingerprint, build_drift_report
from product.protocols.recording_flow import Flow
from product.backend.core.verification.permissions import PermissionContract
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import StorageUnitOfWork
from product.backend.infra.runtime.job_requests import ExecutionRequestStore
from product.protocols.flow_draft import FlowDraft
from product.backend.core.contracts.analysis.canonical import canonical_sha256
from product.backend.workflows.recording.review import FlowDraftReviewer


_SOURCE_FILE_MAX_BYTES = 1_048_576
_DENIED_PATH_MARKERS = (".env", "secret", "credential", "token", ".pem", ".key")


class ContractAnalysis:
    """Contract 来源解析、评估、差异、漂移与历史解析的统一只读入口。"""

    def __init__(
        self,
        uow_factory,
        *,
        var_dir: Path | None = None,
        available_observations: tuple[str, ...] | None = None,
        observer_resolver=None,
    ) -> None:
        self._uow_factory = uow_factory
        self._var_dir = var_dir.resolve() if var_dir is not None else None
        self._available_observations = available_observations
        self._observer_resolver = observer_resolver

    @staticmethod
    def parse_requirement(requirement: Requirement) -> CandidateBatch:
        return parse_requirement(requirement)

    @staticmethod
    def from_flow(project_id: str, flow: Flow | FlowDraft) -> CandidateBatch:
        if isinstance(flow, Flow):
            return build_flow_candidates(project_id, flow)
        try:
            compiled = FlowDraftReviewer().compile(flow)
        except (JiejianError, TypeError, ValidationError):
            return _analysis_issue_batch(
                "recording_flow",
                "flow-draft",
                AnalysisReasonCode.AMBIGUOUS_SOURCE,
                "flow_draft_not_confirmed_or_compilable",
                flow,
            )
        return build_flow_candidates(project_id, compiled)

    @staticmethod
    def from_openapi(project_id: str, document, *, source_locator: str = "openapi") -> CandidateBatch:
        return build_openapi_candidates(project_id, document, source_locator=source_locator)

    @staticmethod
    def from_fastapi_source(
        project_id: str,
        source_path: Path,
        *,
        project_root: Path,
        max_bytes: int = _SOURCE_FILE_MAX_BYTES,
        allowed_suffixes: tuple[str, ...] = (".py",),
    ) -> CandidateBatch:
        """在明确源码根和文件预算内解析 FastAPI 候选，不导入或执行目标模块。"""

        subject = str(source_path)
        try:
            root = project_root.resolve()
            resolved = source_path.resolve()
        except OSError:
            return _analysis_issue_batch(
                "fastapi_ast", subject, AnalysisReasonCode.UNSUPPORTED_SOURCE,
                "source_path_unresolvable", source_path,
            )
        if not resolved.is_relative_to(root):
            return _analysis_issue_batch(
                "fastapi_ast", subject, AnalysisReasonCode.SOURCE_PATH_OUTSIDE_PROJECT,
                "source_path_outside_project", source_path,
            )
        if resolved.suffix.lower() not in {suffix.lower() for suffix in allowed_suffixes} or any(
            marker in part.lower() for part in resolved.parts for marker in _DENIED_PATH_MARKERS
        ):
            return _analysis_issue_batch(
                "fastapi_ast", subject, AnalysisReasonCode.SOURCE_SUFFIX_DENIED,
                "source_suffix_or_path_component_denied", source_path,
            )
        try:
            if not resolved.is_file() or resolved.stat().st_size > max_bytes:
                return _analysis_issue_batch(
                    "fastapi_ast", subject, AnalysisReasonCode.SOURCE_TOO_LARGE,
                    "source_file_missing_or_too_large", source_path,
                )
            raw = resolved.read_bytes()
        except OSError:
            return _analysis_issue_batch(
                "fastapi_ast", subject, AnalysisReasonCode.UNSUPPORTED_SOURCE,
                "source_file_unreadable", source_path,
            )
        try:
            source_text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return _analysis_issue_batch(
                "fastapi_ast", subject, AnalysisReasonCode.AMBIGUOUS_SOURCE,
                "source_file_not_utf8", source_path,
            )
        return parse_fastapi_source_candidates(
            project_id,
            source_text,
            source_locator=resolved.relative_to(root).as_posix(),
            content_sha256=hashlib.sha256(raw).hexdigest(),
        )

    @staticmethod
    def merge(candidates: tuple[ContractCandidate, ...]) -> CandidateMergeResult:
        return merge_candidates(candidates)

    def assess(
        self,
        contract: ContractVersion,
        *,
        candidates: tuple[ContractCandidate, ...] = (),
        source_issues: tuple[AnalysisIssue, ...] = (),
        unexecutable_rule_ids: tuple[str, ...] = (),
    ) -> ContractReviewAssessment:
        return assess_contract(
            contract,
            candidates=candidates,
            source_issues=source_issues,
            available_observations=self._observations_for_project(contract.project_id),
            unexecutable_rule_ids=unexecutable_rule_ids,
        )

    @staticmethod
    def diff(before: ContractVersion, after: ContractVersion) -> ContractVersionDiff:
        return diff_contract_versions(before, after)

    @staticmethod
    def drift(
        contract: ContractVersion,
        **kwargs,
    ) -> DriftReport:
        return build_drift_report(contract, **kwargs)

    def assess_stored_version(
        self,
        project_id: str,
        contract_id: str,
        version: int,
    ) -> ContractReviewAssessment:
        with self._uow_factory() as work:
            contract = work.contract_versions.get(project_id, contract_id, version)
            if contract is None:
                raise JiejianError(ErrorCode.CONTRACT_NOT_FOUND, "契约版本不存在")
            return assess_contract(
                contract,
                candidates=_candidates_for_version(work, contract),
                available_observations=self._observations_for_project(contract.project_id),
            )

    def resolve_run_contract(self, run_id: str) -> ContractHistoryResolution:
        """优先读取 Run 的冻结 Contract 快照；缺失时只返回明确的历史解析状态。"""

        if self._var_dir is None:
            raise JiejianError(ErrorCode.CONTRACT_HISTORY_NOT_FOUND, "历史契约解析需要运行目录")
        with self._uow_factory() as work:
            run = work.runs.get(run_id)
            if run is None:
                raise JiejianError(ErrorCode.CONTRACT_HISTORY_NOT_FOUND, "运行不存在")
            governed = work.contract_versions.get(
                run.project_id,
                run.contract_id,
                run.contract_version,
            )
            job = work.jobs.get_by_run(run_id)
            if job is not None:
                request = ExecutionRequestStore(self._var_dir).load(
                    job.job_id,
                    expected_hash=job.request_hash,
                )
                snapshot = request.project_snapshot
                if (
                    snapshot.project_id != run.project_id
                    or snapshot.contract.id != run.contract_id
                    or snapshot.contract.version != run.contract_version
                ):
                    raise JiejianError(ErrorCode.CONTRACT_HISTORY_NOT_FOUND, "执行请求与运行契约引用不一致")
                return _history_resolution(
                    run_id,
                    run.project_id,
                    snapshot.contract,
                    ContractHistorySource.EXECUTION_REQUEST,
                    execution_job_id=job.job_id,
                    governed_version=governed,
                )
            if governed is not None:
                return _history_resolution(
                    run_id,
                    run.project_id,
                    governed.snapshot,
                    ContractHistorySource.GOVERNED_VERSION,
                    execution_job_id=None,
                    governed_version=governed,
                )
            raise JiejianError(ErrorCode.CONTRACT_HISTORY_NOT_FOUND, "运行没有可定位的契约快照")

    def _observations_for_project(self, project_id: str) -> tuple[str, ...]:
        if self._observer_resolver is not None:
            return self._observer_resolver(project_id)
        return self._available_observations or ("resource_state",)


def _candidates_for_version(work: StorageUnitOfWork, version: ContractVersion) -> tuple[ContractCandidate, ...]:
    candidates: list[ContractCandidate] = []
    for candidate_id in version.provenance.candidate_ids:
        candidate = work.contract_candidates.get(candidate_id)
        if candidate is None:
            raise JiejianError(
                ErrorCode.CONTRACT_ASSESSMENT_BLOCKED,
                "契约引用的候选不存在",
            )
        if candidate.project_id != version.project_id:
            raise JiejianError(
                ErrorCode.CONTRACT_ASSESSMENT_BLOCKED,
                "契约引用了跨项目候选",
            )
        candidates.append(candidate)
    return tuple(candidates)


def _history_resolution(
    run_id: str,
    project_id: str,
    contract: PermissionContract,
    source: ContractHistorySource,
    *,
    execution_job_id: str | None,
    governed_version: ContractVersion | None,
) -> ContractHistoryResolution:
    body = {
        "run_id": run_id,
        "project_id": project_id,
        "contract_id": contract.id,
        "contract_version": contract.version,
        "source": source,
        "contract": contract,
        "execution_job_id": execution_job_id,
    }
    return ContractHistoryResolution(
        run_id=run_id,
        project_id=project_id,
        contract_id=contract.id,
        contract_version=contract.version,
        source=source,
        contract=contract,
        execution_job_id=execution_job_id,
        governed_version=governed_version,
        canonical_sha256=canonical_sha256(body),
    )


def _analysis_issue_batch(
    adapter: str,
    subject_id: str,
    code: AnalysisReasonCode,
    detail: str,
    input_value: object,
) -> CandidateBatch:
    issue = AnalysisIssue(
        code=code,
        severity=AnalysisSeverity.BLOCKING,
        subject_id=subject_id,
        detail=detail,
    )
    return CandidateBatch(
        adapter=adapter,
        issues=(issue,),
        input_sha256=canonical_sha256(
            {"adapter": adapter, "subject_id": subject_id, "code": code, "input": str(input_value)}
        ),
    )


# 仅供本工作流解析契约版本历史的内部模型。
# 历史契约快照结果模型。持久化解析编排位于同目录的 service。

from enum import StrEnum

from pydantic import Field

from product.backend.core.contracts.analysis.models import AnalysisModel
from product.backend.core.contracts.models import ContractVersion
from product.backend.core.identifiers import LONG_SLUG_ID_PATTERN, PROJECT_ID_PATTERN, RUN_ID_PATTERN
from product.backend.core.verification.permissions import PermissionContract


class ContractHistorySource(StrEnum):
    GOVERNED_VERSION = "GOVERNED_VERSION"
    EXECUTION_REQUEST = "EXECUTION_REQUEST"


class ContractHistoryResolution(AnalysisModel):
    run_id: str = Field(pattern=RUN_ID_PATTERN)
    project_id: str = Field(pattern=PROJECT_ID_PATTERN)
    contract_id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    contract_version: int = Field(ge=1)
    source: ContractHistorySource
    contract: PermissionContract
    execution_job_id: str | None = None
    governed_version: ContractVersion | None = None
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

__all__ = ["ContractHistoryResolution", "ContractHistorySource"]
