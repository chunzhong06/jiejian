# =============================================================================
# 受控应用理解分析器
#
# 定位
#   用户显式授权之后、角色和业务动作进入人工确认之前的离线确定性分析边界
#
# 职责
#   有界读取源码｜复用 OpenAPI/FastAPI 静态规则｜生成稳定候选与结构证据
#
# 边界
#   不 import、eval、exec 或启动用户代码，不调用网络/子进程，不读取秘密和生成目录，也不保存源码正文。
#
# 调用链
#   ApplicationUnderstandingService → ApplicationUnderstandingAnalyzer → Core candidates
# =============================================================================

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from pathlib import Path

from product.backend.core.application_understanding import (
    ActionCandidate,
    ActionRiskHint,
    CandidateConfidence,
    CandidateEvidence,
    RoleCandidate,
    candidate_id,
    canonical_role_key,
)
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.onboarding.discovery import (
    canonical_folder,
    is_reparse_point,
)



from .models import (
    AnalysisModel,
    ApplicationAnalysisResult,
    SourceAnalysisLimits,
    _CONFIDENCE_RANK,
    _Finding,
    _IGNORED_DIRECTORIES,
    _METHOD_LABEL,
    _OPENAPI_NAMES,
    _SENSITIVE_FILE,
    _SOURCE_SUFFIXES,
)

from .javascript import JavaScriptAnalysisMixin
from .openapi import OpenApiAnalysisMixin
from .python import PythonAnalysisMixin


class ApplicationUnderstandingAnalyzer(OpenApiAnalysisMixin, PythonAnalysisMixin, JavaScriptAnalysisMixin):
    def __init__(self, *, limits: SourceAnalysisLimits | None = None) -> None:
        self.limits = limits or SourceAnalysisLimits()


    def analyze(
        self,
        project_id: str,
        source_root: str | Path,
    ) -> ApplicationAnalysisResult:
        root = canonical_folder(source_root)
        files = self._read_sources(root)
        roles: dict[str, _Finding] = {}
        actions: dict[str, _Finding] = {}

        for relative, raw in files:
            text = raw.decode("utf-8")
            content_hash = hashlib.sha256(raw).hexdigest()
            suffix = Path(relative).suffix.casefold()
            if Path(relative).name.casefold() in _OPENAPI_NAMES:
                self._analyze_openapi(
                    project_id,
                    relative,
                    text,
                    content_hash,
                    roles,
                    actions,
                )
            elif suffix == ".py":
                self._analyze_python(relative, text, content_hash, roles, actions)
            else:
                self._analyze_javascript(relative, text, content_hash, roles, actions)

        role_candidates = tuple(
            self._role_candidate(key, finding)
            for key, finding in sorted(
                roles.items(),
                key=lambda item: (
                    -_CONFIDENCE_RANK[self._final_confidence(item[1])],
                    item[0],
                ),
            )[: self.limits.max_roles]
        )
        action_candidates = tuple(
            self._action_candidate(key, finding)
            for key, finding in sorted(
                actions.items(),
                key=lambda item: (
                    -_CONFIDENCE_RANK[self._final_confidence(item[1])],
                    item[0],
                ),
            )[: self.limits.max_actions]
        )
        digest = hashlib.sha256()
        for relative, raw in files:
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(raw).digest())
        return ApplicationAnalysisResult(
            source_fingerprint=digest.hexdigest(),
            role_candidates=role_candidates,
            action_candidates=action_candidates,
            files_read=len(files),
            total_bytes=sum(len(raw) for _, raw in files),
        )


    def _read_sources(self, root: Path) -> tuple[tuple[str, bytes], ...]:
        entries_seen = 0
        files_seen = 0
        total_bytes = 0
        values: list[tuple[str, bytes]] = []
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            directory, depth = stack.pop()
            try:
                with os.scandir(directory) as scanner:
                    entries = sorted(scanner, key=lambda item: item.name.casefold())
            except OSError:
                continue
            for entry in entries:
                entries_seen += 1
                if entries_seen > self.limits.max_entries:
                    self._budget_error("源码分析超过目录条目预算")
                path = Path(entry.path)
                try:
                    if is_reparse_point(path):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if (
                            entry.name.casefold() not in _IGNORED_DIRECTORIES
                            and depth < self.limits.max_depth
                        ):
                            stack.append((path, depth + 1))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                lower_name = entry.name.casefold()
                if _SENSITIVE_FILE.search(lower_name):
                    continue
                if path.suffix.casefold() not in _SOURCE_SUFFIXES and lower_name not in _OPENAPI_NAMES:
                    continue
                try:
                    canonical = path.resolve(strict=True)
                    if canonical != root and root not in canonical.parents:
                        continue
                    size = canonical.stat().st_size
                except (OSError, RuntimeError, ValueError):
                    continue
                files_seen += 1
                if files_seen > self.limits.max_files:
                    self._budget_error("源码分析超过文件数量预算")
                if size > self.limits.max_file_bytes:
                    self._budget_error("源码分析文件超过单文件字节预算")
                total_bytes += size
                if total_bytes > self.limits.max_total_bytes:
                    self._budget_error("源码分析超过总字节预算")
                try:
                    raw = canonical.read_bytes()
                    raw.decode("utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                values.append((canonical.relative_to(root).as_posix(), raw))
        values.sort(key=lambda item: item[0].casefold())
        return tuple(values)

    def _add_role(
        self,
        values: dict[str, _Finding],
        raw: str,
        confidence: CandidateConfidence,
        evidence: CandidateEvidence,
    ) -> None:
        try:
            key = canonical_role_key(raw)
        except ValueError:
            return
        finding = values.setdefault(
            key,
            _Finding(display_name=raw.strip()[:128], confidence=confidence),
        )
        self._merge_finding(finding, confidence, evidence)


    def _add_action(
        self,
        values: dict[str, _Finding],
        method: str,
        path: str,
        display_name: str,
        confidence: CandidateConfidence,
        risk_hint: ActionRiskHint,
        evidence: CandidateEvidence,
    ) -> None:
        key = f"{method.upper()} {path}"[:256]
        finding = values.setdefault(
            key,
            _Finding(
                display_name=display_name[:256],
                confidence=confidence,
                risk_hint=risk_hint,
            ),
        )
        if (
            evidence.detector == "openapi-operation"
            and "（待确认名称）" in finding.display_name
            and "（待确认名称）" not in display_name
        ):
            finding.display_name = display_name[:256]
        self._merge_finding(finding, confidence, evidence)


    @staticmethod
    def _merge_finding(
        finding: _Finding,
        confidence: CandidateConfidence,
        evidence: CandidateEvidence,
    ) -> None:
        if _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[finding.confidence]:
            finding.confidence = confidence
        finding.detectors.add(evidence.detector)
        if evidence not in finding.evidence and len(finding.evidence) < 32:
            finding.evidence.append(evidence)


    @staticmethod
    def _final_confidence(finding: _Finding) -> CandidateConfidence:
        if (
            finding.confidence is CandidateConfidence.HIGH
            or len(finding.detectors) >= 2
        ):
            return CandidateConfidence.HIGH
        return finding.confidence


    def _role_candidate(self, key: str, finding: _Finding) -> RoleCandidate:
        return RoleCandidate(
            candidate_id=candidate_id("role", key),
            canonical_key=key,
            display_name=finding.display_name,
            confidence=self._final_confidence(finding),
            evidence=tuple(sorted(finding.evidence, key=self._evidence_key)),
        )


    def _action_candidate(self, key: str, finding: _Finding) -> ActionCandidate:
        return ActionCandidate(
            candidate_id=candidate_id("action", key),
            canonical_key=key,
            display_name=finding.display_name,
            confidence=self._final_confidence(finding),
            risk_hint=finding.risk_hint or ActionRiskHint.UNKNOWN,
            evidence=tuple(sorted(finding.evidence, key=self._evidence_key)),
        )


    @staticmethod
    def _evidence(
        relative: str,
        line_start: int,
        symbol: str | None,
        detector: str,
        content_hash: str,
        line_end: int | None = None,
    ) -> CandidateEvidence:
        return CandidateEvidence(
            relative_path=relative,
            line_start=line_start,
            line_end=line_end or line_start,
            symbol=symbol,
            detector=detector,
            content_sha256=content_hash,
        )


    @staticmethod
    def _evidence_key(item: CandidateEvidence) -> tuple[object, ...]:
        return (
            item.relative_path.casefold(),
            item.line_start,
            item.line_end,
            item.detector,
            item.symbol or "",
        )


    @staticmethod
    def _operation_display(
        method: str,
        path: str,
        operation: Mapping[str, object],
    ) -> str:
        for key in ("summary", "operationId"):
            value = operation.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:256]
        return ApplicationUnderstandingAnalyzer._default_action_display(method, path)


    @staticmethod
    def _default_action_display(method: str, path: str) -> str:
        return f"{_METHOD_LABEL.get(method, method)} {path}（待确认名称）"


    @staticmethod
    def _risk_hint(method: str, path: str) -> ActionRiskHint:
        if method == "GET":
            return ActionRiskHint.READ
        if method == "DELETE":
            return ActionRiskHint.DELETE
        if re.search(r"(?:admin|permission|role|member|invite)", path, re.IGNORECASE):
            return ActionRiskHint.ADMIN
        if method in {"POST", "PUT", "PATCH"}:
            return ActionRiskHint.WRITE
        return ActionRiskHint.UNKNOWN


    @staticmethod
    def _budget_error(message: str) -> None:
        raise JiejianError(ErrorCode.APPLICATION_ANALYSIS_BUDGET, message)
