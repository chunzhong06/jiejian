# 归并角色与业务动作的检测证据，统一置信度、名称优先级和稳定排序。
from __future__ import annotations
import re
from collections.abc import Mapping
from product.backend.domain.applications.models import (
    ActionCandidate,
    ActionRiskHint,
    CandidateConfidence,
    CandidateEvidence,
    RoleCandidate,
    candidate_id,
    canonical_role_key,
)


_CONFIDENCE_RANK = {
    CandidateConfidence.LOW: 0,
    CandidateConfidence.MEDIUM: 1,
    CandidateConfidence.HIGH: 2,
}

_METHOD_LABEL = {
    "GET": "查看",
    "POST": "创建或执行",
    "PUT": "替换",
    "PATCH": "修改",
    "DELETE": "删除",
}


class _Finding:
    def __init__(
        self,
        *,
        display_name: str,
        confidence: CandidateConfidence,
        risk_hint: ActionRiskHint | None = None,
    ) -> None:
        self.display_name = display_name
        self.confidence = confidence
        self.risk_hint = risk_hint
        self.evidence: list[CandidateEvidence] = []
        self.detectors: set[str] = set()


class CandidateCollector:
    """在单次分析内归并检测证据；候选始终保留为待人工确认的建议。"""

    def __init__(self) -> None:
        self._roles: dict[str, _Finding] = {}
        self._actions: dict[str, _Finding] = {}

    def role_candidates(self, limit: int) -> tuple[RoleCandidate, ...]:
        ordered = sorted(
            self._roles.items(),
            key=lambda item: (-_CONFIDENCE_RANK[self._final_confidence(item[1])], item[0]),
        )
        return tuple((self._role_candidate(key, finding) for key, finding in ordered[:limit]))

    def action_candidates(self, limit: int) -> tuple[ActionCandidate, ...]:
        ordered = sorted(
            self._actions.items(),
            key=lambda item: (-_CONFIDENCE_RANK[self._final_confidence(item[1])], item[0]),
        )
        return tuple((self._action_candidate(key, finding) for key, finding in ordered[:limit]))

    def add_role(
        self,
        raw: str,
        confidence: CandidateConfidence,
        evidence: CandidateEvidence,
        *,
        canonical_name: str | None = None,
    ) -> None:
        try:
            key = canonical_role_key(canonical_name or raw)
        except ValueError:
            return
        finding = self._roles.setdefault(
            key, _Finding(display_name=raw.strip()[:128], confidence=confidence)
        )
        self._merge_finding(finding, confidence, evidence)

    def add_action(
        self,
        method: str,
        path: str,
        display_name: str,
        confidence: CandidateConfidence,
        risk_hint: ActionRiskHint,
        evidence: CandidateEvidence,
    ) -> None:
        key = f"{method.upper()} {path}"[:256]
        finding = self._actions.setdefault(
            key,
            _Finding(display_name=display_name[:256], confidence=confidence, risk_hint=risk_hint),
        )
        # 只有 OpenAPI 的明确名称可以替换词法检测生成的待确认名称。
        if (
            evidence.detector == "openapi-operation"
            and "（待确认名称）" in finding.display_name
            and ("（待确认名称）" not in display_name)
        ):
            finding.display_name = display_name[:256]
        self._merge_finding(finding, confidence, evidence)

    @staticmethod
    def _merge_finding(
        finding: _Finding, confidence: CandidateConfidence, evidence: CandidateEvidence
    ) -> None:
        if _CONFIDENCE_RANK[confidence] > _CONFIDENCE_RANK[finding.confidence]:
            finding.confidence = confidence
        finding.detectors.add(evidence.detector)
        if evidence not in finding.evidence and len(finding.evidence) < 32:
            finding.evidence.append(evidence)

    @staticmethod
    def _final_confidence(finding: _Finding) -> CandidateConfidence:
        # 同类检测器的重复命中不提升置信度；不同标签的证据才共同参与提升。
        if finding.confidence is CandidateConfidence.HIGH or len(finding.detectors) >= 2:
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
    def evidence(
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
    def operation_display(method: str, path: str, operation: Mapping[str, object]) -> str:
        for key in ("summary", "operationId"):
            value = operation.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:256]
        return CandidateCollector.default_action_display(method, path)

    @staticmethod
    def default_action_display(method: str, path: str) -> str:
        return f"{_METHOD_LABEL.get(method, method)} {path}（待确认名称）"

    @staticmethod
    def risk_hint(method: str, path: str) -> ActionRiskHint:
        if method == "GET":
            return ActionRiskHint.READ
        if method == "DELETE":
            return ActionRiskHint.DELETE
        if re.search("(?:admin|permission|role|member|invite)", path, re.IGNORECASE):
            return ActionRiskHint.ADMIN
        if method in {"POST", "PUT", "PATCH"}:
            return ActionRiskHint.WRITE
        return ActionRiskHint.UNKNOWN
