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


from product.backend.core.application_understanding import (
    ActionRiskHint,
    CandidateConfidence,
)
from product.backend.core.http_routes import safe_route_path



from .models import (
    _FETCH_REQUEST,
    _Finding,
    _JS_REQUEST,
    _JS_ROLE_STRUCTURE,
    _JS_ROUTE,
    _JS_STRING,
)



class JavaScriptAnalysisMixin:
    def _analyze_javascript(
        self,
        relative: str,
        text: str,
        content_hash: str,
        roles: dict[str, _Finding],
        actions: dict[str, _Finding],
    ) -> None:
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _JS_ROLE_STRUCTURE.search(line):
                for match in _JS_STRING.finditer(line):
                    self._add_role(
                        roles,
                        match.group(2),
                        CandidateConfidence.LOW,
                        self._evidence(
                            relative,
                            line_number,
                            None,
                            "javascript-role-lexical",
                            content_hash,
                        ),
                    )
            for detector, pattern in (
                ("javascript-route", _JS_ROUTE),
                ("frontend-request", _JS_REQUEST),
            ):
                for match in pattern.finditer(line):
                    method, path = match.group(1).upper(), match.group(3)
                    if safe_route_path(path):
                        self._add_action(
                            actions,
                            method,
                            path,
                            self._default_action_display(method, path),
                            CandidateConfidence.MEDIUM,
                            self._risk_hint(method, path),
                            self._evidence(
                                relative,
                                line_number,
                                None,
                                detector,
                                content_hash,
                            ),
                        )
            for match in _FETCH_REQUEST.finditer(line):
                path = match.group(2)
                if safe_route_path(path):
                    self._add_action(
                        actions,
                        "GET",
                        path,
                        self._default_action_display("GET", path),
                        CandidateConfidence.MEDIUM,
                        ActionRiskHint.READ,
                        self._evidence(
                            relative,
                            line_number,
                            None,
                            "frontend-fetch",
                            content_hash,
                        ),
                    )
