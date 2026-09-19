# 保护当前结果 API 的只读转发、Evidence 不可变与目标执行隔离。
from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from product.backend.api.routers.results import build_results_router

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "product/backend"
READ_MODELS = tuple(BACKEND / path for path in (
    "workflows/checks/results.py", "workflows/checks/story.py",
    "workflows/checks/repair.py", "workflows/projects/repair.py",
))


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_result_router_only_registers_current_read_resources() -> None:
    router = build_results_router(SimpleNamespace())
    assert {(route.path, frozenset(route.methods)) for route in router.routes} == {
        (f"/api/runs/{{run_id}}/{suffix}", frozenset({"GET"}))
        for suffix in ("repair-contracts", "result-story", "evidence", "evidence/{evidence_id}")
    }


@pytest.mark.parametrize("suffix,service,method,args,is_list", [
    ("repair-contracts", "check_repairs", "contracts", ("run-a",), True),
    ("result-story", "check_story", "build", ("run-a",), False),
    ("evidence", "check_results", "evidence_index", ("run-a",), True),
    ("evidence/{evidence_id}", "check_results", "evidence", ("run-a", "evidence-a"), False),
])
def test_result_routes_forward_exact_references(suffix, service, method, args, is_list) -> None:
    # 直接调用已注册 endpoint，不启动 HTTP 服务或真实 Reader。
    document = Mock(spec=["model_dump"])
    document.model_dump.return_value = {"fact": "published-only"}
    read = Mock(return_value=(document,) if is_list else document)
    context = SimpleNamespace(**{service: SimpleNamespace(**{method: read})})
    route = next(item for item in build_results_router(context).routes if item.path.endswith("/" + suffix))
    response = route.endpoint(*args)
    read.assert_called_once_with(*args)
    document.model_dump.assert_called_once_with(mode="json")
    expected = [{"fact": "published-only"}] if is_list else {"fact": "published-only"}
    assert json.loads(response.body) == {"schema_version": "1", "data": expected}


def test_no_api_mutator_targets_old_evidence_or_verdict() -> None:
    forbidden = ("evidence", "supplement", "amend", "old-run", "verdict")
    for path in (BACKEND / "api/routers").rglob("*.py"):
        for node in ast.walk(_tree(path)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in {"post", "put", "patch", "delete"}
                    and decorator.args and isinstance(decorator.args[0], ast.Constant)):
                    assert not any(token in str(decorator.args[0].value).casefold() for token in forbidden), path


def test_current_read_models_do_not_execute_targets_or_write_facts() -> None:
    forbidden = (
        "product.backend.infra.observers", "product.backend.infra.execution",
        "product.backend.infra.runtime.runner", "product.backend.infra.runtime.check_runner",
        "product.backend.infra.llm", "httpx", "playwright", "subprocess",
    )
    for path in READ_MODELS:
        imports = set()
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
                assert not {alias.name for alias in node.names} & {
                    "evaluate_check_case", "aggregate_check_verdict",
                }, path
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"evaluate_check_case", "aggregate_check_verdict"}, path
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                # 内存集合的 append/update 不是持久化写入。
                assert node.func.attr not in {
                    "commit", "flush", "execute", "submit", "approve", "write_text", "write_bytes",
                    "run_job", "publish", "unlink", "mkdir",
                    "evaluate_check_case", "aggregate_check_verdict",
                }, (path, node.func.attr)
        assert not {name for name in imports if any(name == p or name.startswith(p + ".") for p in forbidden)}, path


def test_verification_and_read_models_do_not_inspect_live_action_assets() -> None:
    for path in (*READ_MODELS, *(BACKEND / "core/verification").rglob("*.py")):
        assert "inspect_action" not in path.read_text(encoding="utf-8"), path
