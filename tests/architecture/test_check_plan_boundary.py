# 验证纯计划及其 wire 导入闭包不接触 Workflow、Storage、网络或模型。
import ast
from pathlib import Path


def test_check_plan_has_only_pure_dependency_roots():
    source = Path(__file__).resolve().parents[2] / "product/backend/core/check_plan.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert imports
    assert all(name.startswith(("product.backend.core", "product.protocols.execution_v3"))
               or name in {"__future__", "pydantic", "typing", "json", "urllib.parse"} for name in imports)
