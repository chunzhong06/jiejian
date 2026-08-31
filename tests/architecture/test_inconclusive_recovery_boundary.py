# 保护证据不足恢复只读投影、历史发布不可变与前端零重算边界。

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "product/backend"
CONTROL = BACKEND / "workflows/control.py"
RESULTS_ROUTER = BACKEND / "api/routers/results.py"
RESULT_WORKFLOWS = BACKEND / "workflows/results"
VERIFICATION = BACKEND / "core/verification"
RESULT_PAGE = ROOT / "product/frontend/src/features/checks/CheckResultsPage.tsx"
CONTROL_SHELL = ROOT / "product/frontend/src/app/ControlShell.tsx"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def _router_operations(path: Path) -> tuple[tuple[str, str], ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    operations: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                operations.append((decorator.func.attr, decorator.args[0].value))
    return tuple(operations)


def test_published_evidence_routes_are_read_only() -> None:
    evidence_operations = tuple(
        (method, route)
        for method, route in _router_operations(RESULTS_ROUTER)
        if "/evidence" in route
    )

    assert evidence_operations
    assert all(method == "get" for method, _route in evidence_operations)


def test_no_api_mutator_targets_old_evidence_or_verdict() -> None:
    forbidden_targets = ("evidence", "supplement", "amend", "old-run", "verdict")
    for path in (BACKEND / "api/routers").rglob("*.py"):
        for method, route in _router_operations(path):
            if method not in {"post", "put", "patch", "delete"}:
                continue
            assert not any(token in route.casefold() for token in forbidden_targets), (
                path,
                method,
                route,
            )


def test_recovery_and_result_read_models_do_not_reach_target_observers() -> None:
    forbidden = (
        "product.backend.infra.observers",
        "product.backend.infra.runtime.runner",
        "product.backend.infra.execution",
        "httpx",
        "playwright",
    )
    paths = (CONTROL, *RESULT_WORKFLOWS.rglob("*.py"))
    for path in paths:
        imports = _imports(path)
        assert not {
            name
            for name in imports
            if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
        }, path


def test_verification_never_calls_action_asset_inspection() -> None:
    paths = (*VERIFICATION.rglob("*.py"), *RESULT_WORKFLOWS.rglob("*.py"))
    assert not [
        path
        for path in paths
        if "inspect_action" in path.read_text(encoding="utf-8")
    ]


def test_frontend_only_renders_backend_recovery_projection() -> None:
    result_page = RESULT_PAGE.read_text(encoding="utf-8")
    shell = CONTROL_SHELL.read_text(encoding="utf-8")

    assert "inconclusiveRecovery.next_path" in result_page
    assert "inconclusiveRecovery.next_label" in result_page
    assert "inconclusiveRecovery={status?.inconclusive_recovery}" in shell
    for forbidden in (
        "ORIGINAL_PERMISSION_INTENT_CHANGED",
        "intent_hash",
        "policy_fingerprint",
        "完善真实结果确认方式",
    ):
        assert forbidden not in result_page
