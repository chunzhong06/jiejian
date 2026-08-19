# =============================================================================
# OpenAPI Contract 来源适配
#
# 定位
#   有界 OpenAPI 文档到 Contract Candidate 的离线转换器
#
# 职责
#   解析受支持操作｜拒绝外部引用｜提取路径与敏感字段观察点
#
# 调用链
#   ContractAnalysis → build_openapi_candidates → CandidateBatch
# =============================================================================

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from product.backend.core.contracts.models import CandidateSuggestion, CandidateRiskKind
from product.backend.core.contracts.models import ContractCandidate, ContractSourceType
from product.backend.core.contracts.analysis.models import AnalysisIssue, AnalysisReasonCode, AnalysisSeverity, CandidateBatch
from product.backend.core.contracts.analysis.canonical import _candidate, _issue, _issue_key, _rule_id, canonical_sha256


_SENSITIVE_FIELD = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[_-]?key|"
    r"id[_-]?card|ssn|email|phone|address|full[_-]?name)",
    re.IGNORECASE,
)
_HTTP_METHODS = ("GET", "PATCH", "POST", "PUT", "DELETE")
_OPENAPI_MAX_BYTES = 1_048_576


def build_openapi_candidates(
    project_id: str,
    document: Mapping[str, Any],
    *,
    source_locator: str = "openapi",
    max_bytes: int = _OPENAPI_MAX_BYTES,
) -> CandidateBatch:
    """消费受控 OpenAPI Mapping；不解析外部文件引用。"""

    document_hash = canonical_sha256(document)
    if not isinstance(document, Mapping):
        return CandidateBatch(
            adapter="openapi",
            issues=(_issue(AnalysisReasonCode.INVALID_OPENAPI, AnalysisSeverity.BLOCKING, source_locator, detail="openapi_document_not_mapping"),),
            input_sha256=document_hash,
        )
    if len(json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")) > max_bytes:
        return CandidateBatch(
            adapter="openapi",
            issues=(_issue(AnalysisReasonCode.SOURCE_TOO_LARGE, AnalysisSeverity.BLOCKING, source_locator, detail="openapi_document_too_large"),),
            input_sha256=document_hash,
        )
    if not isinstance(document.get("paths"), Mapping) or not (
        document.get("openapi") or document.get("swagger")
    ):
        return CandidateBatch(
            adapter="openapi",
            issues=(_issue(AnalysisReasonCode.INVALID_OPENAPI, AnalysisSeverity.BLOCKING, source_locator, detail="openapi_root_invalid"),),
            input_sha256=document_hash,
        )
    if _contains_external_ref(document):
        return CandidateBatch(
            adapter="openapi",
            issues=(_issue(AnalysisReasonCode.INVALID_OPENAPI, AnalysisSeverity.BLOCKING, source_locator, detail="external_reference_denied"),),
            input_sha256=document_hash,
        )
    candidates: list[ContractCandidate] = []
    issues: list[AnalysisIssue] = []
    for path, path_item in sorted(document["paths"].items(), key=lambda item: str(item[0])):
        if not isinstance(path, str) or not _safe_route_path(path):
            issues.append(_issue(AnalysisReasonCode.INVALID_OPENAPI, AnalysisSeverity.BLOCKING, str(path), detail="openapi_path_invalid"))
            continue
        if not isinstance(path_item, Mapping):
            issues.append(_issue(AnalysisReasonCode.AMBIGUOUS_SOURCE, AnalysisSeverity.BLOCKING, f"{source_locator}:{path}", detail="openapi_path_item_invalid"))
            continue
        for method, operation in sorted(path_item.items(), key=lambda item: str(item[0])):
            method_upper = str(method).upper()
            if method_upper in {"PARAMETERS", "SUMMARY", "DESCRIPTION", "SERVERS"}:
                continue
            if method_upper not in _HTTP_METHODS:
                issues.append(_issue(AnalysisReasonCode.UNSUPPORTED_SOURCE, AnalysisSeverity.WARNING, f"{source_locator}:{path}:{method}", detail="openapi_method_unsupported"))
                continue
            if not isinstance(operation, Mapping):
                issues.append(_issue(AnalysisReasonCode.AMBIGUOUS_SOURCE, AnalysisSeverity.BLOCKING, f"{source_locator}:{path}:{method_upper}", detail="openapi_operation_invalid"))
                continue
            kind = CandidateRiskKind.FOREIGN_READ if method_upper == "GET" else CandidateRiskKind.UNAUTHORIZED_SIDE_EFFECT
            observations = ("resource_state",)
            candidates.append(
                _candidate(
                    project_id,
                    ContractSourceType.STATIC_ANALYSIS,
                    f"{source_locator}:{method_upper}:{path}",
                    document_hash,
                    CandidateSuggestion(
                        schema_version="1",
                        id=_rule_id("route", method_upper.lower(), path, kind.value),
                        kind=kind,
                        required_observations=observations,
                        severity="critical" if kind is not CandidateRiskKind.FOREIGN_READ else "high",
                    ),
                )
            )
            for field in _openapi_sensitive_fields(operation):
                candidates.append(
                    _candidate(
                        project_id,
                        ContractSourceType.STATIC_ANALYSIS,
                        f"{source_locator}:{method_upper}:{path}:field:{field}",
                        document_hash,
                        CandidateSuggestion(
                            schema_version="1",
                            id=_rule_id("route", method_upper.lower(), path, "privileged-field", field),
                            kind=CandidateRiskKind.PRIVILEGED_FIELD,
                            required_observations=("resource_state",),
                            severity="critical",
                        ),
                    )
                )
    return CandidateBatch(
        adapter="openapi",
        candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
        issues=tuple(sorted(issues, key=_issue_key)),
        input_sha256=document_hash,
    )

def _safe_route_path(path: str) -> bool:
    return bool(path.startswith("/") and not path.startswith("//") and ".." not in path.split("/"))


def _contains_external_ref(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "$ref" and (not isinstance(item, str) or not item.startswith("#/")):
                return True
            if _contains_external_ref(item):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_external_ref(item) for item in value)
    return False


def _openapi_sensitive_fields(operation: Mapping[str, Any]) -> tuple[str, ...]:
    fields: set[str] = set()
    parameters = operation.get("parameters", ())
    if isinstance(parameters, list):
        for parameter in parameters:
            if isinstance(parameter, Mapping) and isinstance(parameter.get("name"), str) and _SENSITIVE_FIELD.search(parameter["name"]):
                fields.add(parameter["name"])
    body = operation.get("requestBody")
    if isinstance(body, Mapping):
        content = body.get("content")
        if isinstance(content, Mapping):
            for media in content.values():
                if isinstance(media, Mapping):
                    schema = media.get("schema")
                    if isinstance(schema, Mapping) and isinstance(schema.get("properties"), Mapping):
                        fields.update(
                            name for name in schema["properties"] if isinstance(name, str) and _SENSITIVE_FIELD.search(name)
                        )
    return tuple(sorted(fields))
