# =============================================================================
# FastAPI AST Contract 来源适配
#
# 定位
#   不执行应用源码的确定性 Contract Candidate 发现器
#
# 职责
#   解析路由装饰器｜限制可接受字面量｜记录无法证明的来源问题
#
# 调用链
#   ContractAnalysisService → parse_fastapi_source_candidates → CandidateBatch
# =============================================================================

from __future__ import annotations

import ast
import hashlib

from ....verification.models import ContractRule, RuleKind
from ...models import ContractCandidate, ContractSourceType
from ..models import AnalysisIssue, AnalysisReasonCode, AnalysisSeverity, CandidateBatch
from ..canonical import _candidate, _issue, _issue_key, _rule_id
from .openapi import _HTTP_METHODS, _SENSITIVE_FIELD, _safe_route_path


def parse_fastapi_source_candidates(
    project_id: str,
    source: str | bytes,
    *,
    source_locator: str,
    content_sha256: str,
) -> CandidateBatch:
    """只解析 Application 已授权提供的 Python 源文本，不读取文件。"""

    raw = source.encode("utf-8") if isinstance(source, str) else source
    source_hash = hashlib.sha256(raw).hexdigest()
    if content_sha256 != source_hash:
        return CandidateBatch(
            adapter="fastapi_ast_v1",
            issues=(_issue(AnalysisReasonCode.SOURCE_HASH_MISMATCH, AnalysisSeverity.BLOCKING, source_locator, detail="source_content_hash_mismatch"),),
            input_sha256=source_hash,
        )
    try:
        tree = ast.parse(raw.decode("utf-8"), filename=source_locator)
    except (UnicodeDecodeError, SyntaxError):
        return CandidateBatch(
            adapter="fastapi_ast_v1",
            issues=(_issue(AnalysisReasonCode.AMBIGUOUS_SOURCE, AnalysisSeverity.BLOCKING, source_locator, detail="python_source_not_parseable"),),
            input_sha256=source_hash,
        )
    candidates: list[ContractCandidate] = []
    issues: list[AnalysisIssue] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            target = call.func if call is not None else decorator
            method = target.attr.upper() if isinstance(target, ast.Attribute) else None
            if method not in _HTTP_METHODS:
                continue
            path_node = call.args[0] if call is not None and call.args else None
            if not isinstance(path_node, ast.Constant) or not isinstance(path_node.value, str) or not _safe_route_path(path_node.value):
                issues.append(_issue(AnalysisReasonCode.AMBIGUOUS_SOURCE, AnalysisSeverity.BLOCKING, f"{source_locator}:line:{node.lineno}", detail="fastapi_route_path_not_literal"))
                continue
            path = path_node.value
            kind = RuleKind.FOREIGN_READ if method == "GET" else RuleKind.UNAUTHORIZED_SIDE_EFFECT
            observers = ("http",) if kind is RuleKind.FOREIGN_READ else ("http", "owner_api")
            locator = f"{source_locator}:line:{node.lineno}:{method}:{path}"
            candidates.append(
                _candidate(
                    project_id,
                    ContractSourceType.STATIC_ANALYSIS,
                    locator,
                    source_hash,
                    ContractRule(
                        schema_version="1",
                        id=_rule_id("route", method.lower(), path, kind.value),
                        kind=kind,
                        required_observers=observers,
                        severity="critical" if kind is not RuleKind.FOREIGN_READ else "high",
                    ),
                )
            )
            for argument in (*node.args.args, *node.args.kwonlyargs):
                if _SENSITIVE_FIELD.search(argument.arg):
                    candidates.append(
                        _candidate(
                            project_id,
                            ContractSourceType.STATIC_ANALYSIS,
                            f"{locator}:field:{argument.arg}",
                            source_hash,
                            ContractRule(
                                schema_version="1",
                                id=_rule_id("route", method.lower(), path, "privileged-field", argument.arg),
                                kind=RuleKind.PRIVILEGED_FIELD,
                                required_observers=("http", "owner_api"),
                                severity="critical",
                            ),
                        )
                    )
    if not candidates and not issues:
        issues.append(_issue(AnalysisReasonCode.UNSUPPORTED_SOURCE, AnalysisSeverity.WARNING, source_locator, detail="no_static_fastapi_routes_found"))
    return CandidateBatch(
        adapter="fastapi_ast_v1",
        candidates=tuple(sorted(candidates, key=lambda item: item.candidate_id)),
        issues=tuple(sorted(issues, key=_issue_key)),
        input_sha256=source_hash,
    )
