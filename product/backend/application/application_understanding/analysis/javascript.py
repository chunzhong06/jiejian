# 静态识别 JavaScript 与 TypeScript 中的角色和请求线索，结果只作为候选。
from __future__ import annotations
import re
from product.backend.domain.applications.models import ActionRiskHint, CandidateConfidence
from product.backend.domain.http_routes import safe_route_path
from product.backend.application.application_understanding.analysis.findings import (
    CandidateCollector,
)


_JS_ROLE_STRUCTURE = re.compile(
    "\\b(?:const|let|var)\\s+[A-Za-z0-9_$]*(?:role|group|access_?level)s?\\b\\s*=|\\b(?:require|has|check|ensure|allow)(?:Role|Group|AccessLevel)\\s*\\(",
    re.IGNORECASE,
)


_JS_STRING = re.compile("(['\\\"])([A-Za-z][A-Za-z0-9_.:-]{0,63})\\1")


_JS_ROUTE = re.compile(
    "\\b(?:app|router)\\s*\\.\\s*(get|post|put|patch|delete)\\s*\\(\\s*(['\\\"])(/[^'\\\"]*)\\2",
    re.IGNORECASE,
)


_JS_REQUEST = re.compile(
    "\\b(?:axios|client|api|request)\\s*\\.\\s*(get|post|put|patch|delete)\\s*\\(\\s*(['\\\"])(/[^'\\\"]*)\\2",
    re.IGNORECASE,
)


_FETCH_REQUEST = re.compile("\\bfetch\\s*\\(\\s*(['\\\"])(/[^'\\\"]*)\\1")


def analyze_javascript(
    findings: CandidateCollector, relative: str, text: str, content_hash: str
) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if _JS_ROLE_STRUCTURE.search(line):
            for match in _JS_STRING.finditer(line):
                findings.add_role(
                    match.group(2),
                    CandidateConfidence.LOW,
                    findings.evidence(
                        relative, line_number, None, "javascript-role-lexical", content_hash
                    ),
                )
        for detector, pattern in (
            ("javascript-route", _JS_ROUTE),
            ("frontend-request", _JS_REQUEST),
        ):
            for match in pattern.finditer(line):
                method, path = (match.group(1).upper(), match.group(3))
                if safe_route_path(path):
                    findings.add_action(
                        method,
                        path,
                        findings.default_action_display(method, path),
                        CandidateConfidence.MEDIUM,
                        findings.risk_hint(method, path),
                        findings.evidence(relative, line_number, None, detector, content_hash),
                    )
        for match in _FETCH_REQUEST.finditer(line):
            path = match.group(2)
            if safe_route_path(path):
                findings.add_action(
                    "GET",
                    path,
                    findings.default_action_display("GET", path),
                    CandidateConfidence.MEDIUM,
                    ActionRiskHint.READ,
                    findings.evidence(relative, line_number, None, "frontend-fetch", content_hash),
                )
