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

import json
from collections.abc import Mapping
import yaml

from product.backend.core.application_understanding import (
    CandidateConfidence,
)
from product.backend.core.http_routes import HTTP_METHODS, safe_route_path
from product.backend.workflows.onboarding.discovery import (
    canonical_folder,
    is_reparse_point,
)



from .models import _Finding



class OpenApiAnalysisMixin:
    @staticmethod
    def _extension_roles(value: object) -> tuple[tuple[str, str], ...]:
        if isinstance(value, str):
            return ((value, value),)
        if isinstance(value, Mapping):
            return tuple(
                (str(key), display if isinstance(display, str) else str(key))
                for key, display in value.items()
            )
        if isinstance(value, (list, tuple)):
            return tuple((item, item) for item in value if isinstance(item, str))
        return ()

    def _analyze_openapi(
        self,
        project_id: str,
        relative: str,
        text: str,
        content_hash: str,
        roles: dict[str, _Finding],
        actions: dict[str, _Finding],
    ) -> None:
        try:
            document = (
                json.loads(text)
                if relative.casefold().endswith(".json")
                else yaml.safe_load(text)
            )
        except (json.JSONDecodeError, yaml.YAMLError):
            return
        if not isinstance(document, Mapping):
            return
        if not _valid_openapi_document(document, max_bytes=self.limits.max_file_bytes):
            return
        for canonical_name, display_name in self._openapi_roles(document):
            self._add_role(
                roles,
                display_name,
                CandidateConfidence.HIGH,
                self._evidence(relative, 1, None, "openapi-role-extension", content_hash),
                canonical_name=canonical_name,
            )
        paths = document.get("paths")
        if not isinstance(paths, Mapping):
            return
        for path, item in sorted(paths.items(), key=lambda value: str(value[0])):
            if not isinstance(path, str) or not safe_route_path(path) or not isinstance(item, Mapping):
                continue
            for method, operation in sorted(item.items(), key=lambda value: str(value[0])):
                upper = str(method).upper()
                if upper not in HTTP_METHODS or not isinstance(operation, Mapping):
                    continue
                display = self._operation_display(upper, path, operation)
                symbol = operation.get("operationId")
                self._add_action(
                    actions,
                    upper,
                    path,
                    display,
                    CandidateConfidence.MEDIUM,
                    self._risk_hint(upper, path),
                    self._evidence(
                        relative,
                        1,
                        symbol if isinstance(symbol, str) else None,
                        "openapi-operation",
                        content_hash,
                    ),
                )


    @staticmethod
    def _openapi_roles(document: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
        """只读取显式供应商角色扩展，OAuth scopes 不等同于应用权限组。"""

        roles: dict[str, str] = {}
        pending: list[object] = [document]
        seen = 0
        while pending and seen < 512:
            value = pending.pop()
            seen += 1
            if isinstance(value, Mapping):
                for key, nested in value.items():
                    if str(key).casefold() in {
                        "x-role",
                        "x-roles",
                        "x-group",
                        "x-groups",
                        "x-access-levels",
                    }:
                        roles.update(OpenApiAnalysisMixin._extension_roles(nested))
                    else:
                        pending.append(nested)
            elif isinstance(value, (list, tuple)):
                pending.extend(value)
        return tuple(sorted(roles.items()))


def _valid_openapi_document(document: Mapping[str, object], *, max_bytes: int) -> bool:
    """只接受可在当前文件内完整解释的有界 OpenAPI 结构。"""

    try:
        if len(json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")) > max_bytes:
            return False
    except (TypeError, ValueError):
        return False
    paths = document.get("paths")
    if not (document.get("openapi") or document.get("swagger")) or not isinstance(paths, Mapping):
        return False
    if _contains_external_ref(document):
        return False
    for path, path_item in paths.items():
        if not isinstance(path, str) or not safe_route_path(path) or not isinstance(path_item, Mapping):
            return False
        for method, operation in path_item.items():
            upper = str(method).upper()
            if upper in {"PARAMETERS", "SUMMARY", "DESCRIPTION", "SERVERS"}:
                continue
            if upper in HTTP_METHODS and not isinstance(operation, Mapping):
                return False
    return True


def _contains_external_ref(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if key == "$ref" and (not isinstance(nested, str) or not nested.startswith("#/")):
                return True
            if _contains_external_ref(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_external_ref(item) for item in value)
    return False
