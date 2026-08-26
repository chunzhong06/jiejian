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

import ast

from product.backend.core.application_understanding import (
    CandidateConfidence,
)
from product.backend.core.http_routes import HTTP_METHODS, safe_route_path



from .models import _Finding, _ROLE_CLASS, _ROLE_CONTEXT, _ROLE_GUARD



class PythonAnalysisMixin:
    def _analyze_python(
        self,
        relative: str,
        text: str,
        content_hash: str,
        roles: dict[str, _Finding],
        actions: dict[str, _Finding],
    ) -> None:
        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError:
            return
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and self._is_role_enum(node):
                for child in node.body:
                    if isinstance(child, (ast.Assign, ast.AnnAssign)):
                        value = child.value
                        if isinstance(value, ast.Constant) and isinstance(value.value, str):
                            self._add_role(
                                roles,
                                value.value,
                                CandidateConfidence.HIGH,
                                self._evidence(
                                    relative,
                                    child.lineno,
                                    node.name,
                                    "python-role-enum",
                                    content_hash,
                                    getattr(child, "end_lineno", child.lineno),
                                ),
                            )
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                names = self._assignment_names(node)
                confidence = (
                    CandidateConfidence.MEDIUM
                    if any(_ROLE_CONTEXT.search(name) for name in names)
                    else CandidateConfidence.LOW
                )
                if confidence is CandidateConfidence.MEDIUM:
                    for value in self._literal_strings(node.value):
                        self._add_role(
                            roles,
                            value,
                            confidence,
                            self._evidence(
                                relative,
                                node.lineno,
                                names[0] if names else None,
                                "python-role-constant",
                                content_hash,
                                getattr(node, "end_lineno", node.lineno),
                            ),
                        )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._python_route(relative, node, content_hash, actions)
            if isinstance(node, ast.Call) and _ROLE_GUARD.fullmatch(
                self._call_name(node.func)
            ):
                for value in self._literal_strings_from_nodes(node.args):
                    self._add_role(
                        roles,
                        value,
                        CandidateConfidence.HIGH,
                        self._evidence(
                            relative,
                            node.lineno,
                            self._call_name(node.func),
                            "python-role-guard",
                            content_hash,
                            getattr(node, "end_lineno", node.lineno),
                        ),
                    )
            if isinstance(node, ast.Compare):
                for value in self._role_compare_strings(node):
                    self._add_role(
                        roles,
                        value,
                        CandidateConfidence.HIGH,
                        self._evidence(
                            relative,
                            node.lineno,
                            None,
                            "python-role-field-compare",
                            content_hash,
                            getattr(node, "end_lineno", node.lineno),
                        ),
                    )


    def _python_route(
        self,
        relative: str,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        content_hash: str,
        actions: dict[str, _Finding],
    ) -> None:
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            target = call.func if call is not None else decorator
            method = target.attr.upper() if isinstance(target, ast.Attribute) else None
            path_node = call.args[0] if call is not None and call.args else None
            if (
                method not in HTTP_METHODS
                or not isinstance(path_node, ast.Constant)
                or not isinstance(path_node.value, str)
                or not safe_route_path(path_node.value)
            ):
                continue
            self._add_action(
                actions,
                method,
                path_node.value,
                self._default_action_display(method, path_node.value),
                CandidateConfidence.MEDIUM,
                self._risk_hint(method, path_node.value),
                self._evidence(
                    relative,
                    node.lineno,
                    node.name,
                    "fastapi-route-ast",
                    content_hash,
                    getattr(node, "end_lineno", node.lineno),
                ),
            )


    @staticmethod
    def _call_name(value: ast.AST) -> str:
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            return value.attr
        return ""


    @staticmethod
    def _literal_strings_from_nodes(values: list[ast.AST]) -> tuple[str, ...]:
        return tuple(
            value.value
            for value in values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )


    @staticmethod
    def _role_compare_strings(node: ast.Compare) -> tuple[str, ...]:
        values = (node.left, *node.comparators)
        has_role_field = any(
            isinstance(value, ast.Attribute)
            and _ROLE_CONTEXT.fullmatch(value.attr)
            for value in values
        )
        if not has_role_field:
            return ()
        return tuple(
            value.value
            for value in values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )


    @staticmethod
    def _assignment_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names: list[str] = []
        for target in targets:
            if isinstance(target, ast.Name):
                names.append(target.id)
            elif isinstance(target, ast.Attribute):
                names.append(target.attr)
        return tuple(names)


    @staticmethod
    def _literal_strings(value: ast.AST | None) -> tuple[str, ...]:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return (value.value,)
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            return tuple(
                item.value
                for item in value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
        if isinstance(value, ast.Dict):
            return tuple(
                item.value
                for item in (*value.keys, *value.values)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
        return ()


    @staticmethod
    def _is_role_enum(node: ast.ClassDef) -> bool:
        base_names = {
            base.id
            if isinstance(base, ast.Name)
            else base.attr
            if isinstance(base, ast.Attribute)
            else ""
            for base in node.bases
        }
        return bool(
            _ROLE_CLASS.search(node.name)
            and base_names & {"Enum", "StrEnum"}
        )
