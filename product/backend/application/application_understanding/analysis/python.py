# 静态识别 Python 角色与路由，不导入或执行被分析代码。
from __future__ import annotations
import ast
import re
from product.backend.domain.applications.models import CandidateConfidence
from product.backend.domain.http_routes import HTTP_METHODS, safe_route_path
from product.backend.application.application_understanding.analysis.findings import (
    CandidateCollector,
)


_ROLE_CONTEXT = re.compile(
    "(?<![A-Za-z0-9])(?:role|roles|group|groups|access[_-]?levels?)(?![A-Za-z0-9])", re.IGNORECASE
)


_ROLE_CLASS = re.compile("(?:role|group|access_?level)", re.IGNORECASE)


_ROLE_GUARD = re.compile(
    "^(?:require|has|check|ensure|allow)_(?:role|group|access_level)$|^(?:role|group|access_level)_guard$",
    re.IGNORECASE,
)


def analyze_python(
    findings: CandidateCollector, relative: str, text: str, content_hash: str
) -> None:
    try:
        tree = ast.parse(text, filename=relative)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _is_role_enum(node):
            for child in node.body:
                if isinstance(child, (ast.Assign, ast.AnnAssign)):
                    value = child.value
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        findings.add_role(
                            value.value,
                            CandidateConfidence.HIGH,
                            findings.evidence(
                                relative,
                                child.lineno,
                                node.name,
                                "python-role-enum",
                                content_hash,
                                getattr(child, "end_lineno", child.lineno),
                            ),
                        )
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            names = _assignment_names(node)
            confidence = (
                CandidateConfidence.MEDIUM
                if any((_ROLE_CONTEXT.search(name) for name in names))
                else CandidateConfidence.LOW
            )
            if confidence is CandidateConfidence.MEDIUM:
                for value in _literal_strings(node.value):
                    findings.add_role(
                        value,
                        confidence,
                        findings.evidence(
                            relative,
                            node.lineno,
                            names[0] if names else None,
                            "python-role-constant",
                            content_hash,
                            getattr(node, "end_lineno", node.lineno),
                        ),
                    )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _python_route(findings, relative, node, content_hash)
        if isinstance(node, ast.Call) and _ROLE_GUARD.fullmatch(_call_name(node.func)):
            for value in _literal_strings_from_nodes(node.args):
                findings.add_role(
                    value,
                    CandidateConfidence.HIGH,
                    findings.evidence(
                        relative,
                        node.lineno,
                        _call_name(node.func),
                        "python-role-guard",
                        content_hash,
                        getattr(node, "end_lineno", node.lineno),
                    ),
                )
        if isinstance(node, ast.Compare):
            for value in _role_compare_strings(node):
                findings.add_role(
                    value,
                    CandidateConfidence.HIGH,
                    findings.evidence(
                        relative,
                        node.lineno,
                        None,
                        "python-role-field-compare",
                        content_hash,
                        getattr(node, "end_lineno", node.lineno),
                    ),
                )


def _python_route(
    findings: CandidateCollector,
    relative: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    content_hash: str,
) -> None:
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        target = call.func if call is not None else decorator
        method = target.attr.upper() if isinstance(target, ast.Attribute) else None
        path_node = call.args[0] if call is not None and call.args else None
        if (
            method not in HTTP_METHODS
            or not isinstance(path_node, ast.Constant)
            or (not isinstance(path_node.value, str))
            or (not safe_route_path(path_node.value))
        ):
            continue
        findings.add_action(
            method,
            path_node.value,
            findings.default_action_display(method, path_node.value),
            CandidateConfidence.MEDIUM,
            findings.risk_hint(method, path_node.value),
            findings.evidence(
                relative,
                node.lineno,
                node.name,
                "fastapi-route-ast",
                content_hash,
                getattr(node, "end_lineno", node.lineno),
            ),
        )


def _call_name(value: ast.AST) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return ""


def _literal_strings_from_nodes(values: list[ast.AST]) -> tuple[str, ...]:
    return tuple(
        (
            value.value
            for value in values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    )


def _role_compare_strings(node: ast.Compare) -> tuple[str, ...]:
    values = (node.left, *node.comparators)
    has_role_field = any(
        (
            isinstance(value, ast.Attribute) and _ROLE_CONTEXT.fullmatch(value.attr)
            for value in values
        )
    )
    if not has_role_field:
        return ()
    return tuple(
        (
            value.value
            for value in values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    )


def _assignment_names(node: ast.Assign | ast.AnnAssign) -> tuple[str, ...]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names: list[str] = []
    for target in targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, ast.Attribute):
            names.append(target.attr)
    return tuple(names)


def _literal_strings(value: ast.AST | None) -> tuple[str, ...]:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return (value.value,)
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return tuple(
            (
                item.value
                for item in value.elts
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
        )
    if isinstance(value, ast.Dict):
        return tuple(
            (
                item.value
                for item in (*value.keys, *value.values)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
        )
    return ()


def _is_role_enum(node: ast.ClassDef) -> bool:
    base_names = {
        base.id
        if isinstance(base, ast.Name)
        else base.attr
        if isinstance(base, ast.Attribute)
        else ""
        for base in node.bases
    }
    return bool(_ROLE_CLASS.search(node.name) and base_names & {"Enum", "StrEnum"})
