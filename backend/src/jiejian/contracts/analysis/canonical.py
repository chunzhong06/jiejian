# =============================================================================
# Contract 分析规范化
#
# 定位
#   候选、问题与规则身份计算共享的确定性基础
#
# 职责
#   生成规范 JSON 摘要｜构造稳定 ID｜统一问题排序键
#
# 调用链
#   Sources / Merge / Drift → canonical helpers → stable analysis models
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from enum import Enum
from typing import Any

from pydantic import BaseModel

from ..models import ContractCandidate, ContractSourceType, SourceReference
from ...verification.models import ContractRule
from .models import AnalysisIssue, AnalysisReasonCode, AnalysisSeverity


def canonical_sha256(value: Any) -> str:
    """对纯数据计算规范 SHA-256；不读取文件或调用外部服务。"""

    payload = _jsonable(value)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value

def _candidate(
    project_id: str,
    source_type: ContractSourceType,
    locator: str,
    content_sha256: str,
    rule: ContractRule,
    *,
    requirement_ids: tuple[str, ...] = (),
) -> ContractCandidate:
    fingerprint = canonical_sha256(
        {
            "project_id": project_id,
            "source_type": source_type,
            "locator": locator,
            "content_sha256": content_sha256,
            "rule": rule,
            "requirement_ids": requirement_ids,
        }
    )
    return ContractCandidate(
        candidate_id=f"cand_{fingerprint[:32]}",
        project_id=project_id,
        source=SourceReference(
            source_type=source_type,
            locator=locator,
            content_sha256=content_sha256,
        ),
        rule=rule,
        requirement_ids=requirement_ids,
        created_by="deterministic-analyzer",
        created_at_us=0,
    )


def _issue(
    code: AnalysisReasonCode,
    severity: AnalysisSeverity,
    subject_id: str,
    *,
    detail: str,
    candidate_ids: tuple[str, ...] = (),
    requirement_ids: tuple[str, ...] = (),
) -> AnalysisIssue:
    return AnalysisIssue(
        code=code,
        severity=severity,
        subject_id=subject_id,
        candidate_ids=tuple(sorted(candidate_ids)),
        requirement_ids=tuple(sorted(requirement_ids)),
        detail=detail,
    )


def _issue_key(issue: AnalysisIssue) -> tuple[str, str, str, tuple[str, ...], tuple[str, ...]]:
    return (issue.code.value, issue.severity.value, issue.subject_id, issue.candidate_ids, issue.requirement_ids)


def _rule_id(*parts: str) -> str:
    slug = "-".join(re.sub(r"[^a-z0-9]+", "-", part.lower()).strip("-") for part in parts)
    if not slug or not slug[0].isalpha():
        slug = "rule-" + slug
    if len(slug) > 120:
        slug = slug[:80] + "-" + hashlib.sha256(slug.encode("utf-8")).hexdigest()[:32]
    return slug
