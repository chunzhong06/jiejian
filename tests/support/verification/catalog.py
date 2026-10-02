# 读取测试能力目录并计算保守影响范围；未知改动不能静默缩小验证。
from __future__ import annotations

import ast
import hashlib
import platform
import subprocess
import sys
import tomllib
from pathlib import Path


def catalog(root: Path) -> dict:
    value = tomllib.loads((root / "tests/suites.toml").read_text(encoding="utf-8"))
    if value.get("schema_version") != "1":
        raise ValueError("TEST_CATALOG_VERSION")
    for area in value["areas"].values():
        for path in area["tests"] + area["sources"]:
            if Path(path).is_absolute() or ".." in Path(path).parts or not (root / path).exists():
                raise ValueError("TEST_CATALOG_PATH")
    return value["areas"]


def is_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def source_files(root: Path) -> list[str]:
    # 包括未提交新文件和删除文件；Git HEAD 不能代表一个脏工作树的测试身份。
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=root, check=True, capture_output=True)
    return sorted(set(result.stdout.decode("utf-8").split("\0")) - {""})


def fingerprint(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(set(paths)):
        path = root / name
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"<deleted>")
        digest.update(b"\0")
    return digest.hexdigest()


def test_dependencies(root: Path, selected: set[str]) -> set[str]:
    """追踪测试间静态导入；共享 fixture/support 仍保守整体纳入。"""
    visited = set()
    pending = list(selected)
    while pending:
        name = pending.pop()
        if name in visited or not (root / name).is_file():
            continue
        visited.add(name)
        if not name.endswith(".py"):
            continue
        tree = ast.parse((root / name).read_text(encoding="utf-8-sig"))
        modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parent = name.removesuffix(".py").split("/")[:-node.level]
                    base = ".".join(parent + ([base] if base else []))
                modules.append(base)
                modules.extend(base + "." + alias.name for alias in node.names)
        for module in modules:
            if module.startswith("tests."):
                pending.extend([module.replace(".", "/") + ".py", module.replace(".", "/") + "/__init__.py"])
    return visited


def inventory(root: Path) -> dict:
    areas = catalog(root)
    files = []
    for name in source_files(root):
        path = root / name
        python_test = name.startswith("tests/") and path.name.startswith("test_") and path.suffix == ".py"
        frontend_test = name.startswith("product/frontend/src/") and (name.endswith(".test.ts") or name.endswith(".test.tsx"))
        if not path.is_file() or not (python_test or frontend_test):
            continue
        owners = [key for key, value in areas.items() if any(is_under(name, p) for p in value["tests"])]
        if not owners:
            raise ValueError(f"TEST_WITHOUT_CAPABILITY:{name}")
        functions = None
        if python_test:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            functions = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_") for n in ast.walk(tree))
        files.append({"path": name, "areas": owners, "functions": functions,
                      "engine": "pytest" if python_test else "vitest"})
    return {"schema_version": "1", "files": files, "invariants": {k: v["invariants"] for k, v in areas.items()}}


def plan(root: Path, *, level: str, areas: list[str], changed: list[str], l5: list[str]) -> dict:
    definitions = catalog(root)
    unknown = set(areas) - set(definitions) - {"all"}
    if unknown:
        raise ValueError("UNKNOWN_TEST_AREA:" + ",".join(sorted(unknown)))
    normalized = [p.replace("\\", "/").removeprefix("./") for p in changed]
    if any(Path(p).is_absolute() or ".." in Path(p).parts or ":" in p for p in normalized):
        raise ValueError("CHANGED_PATH_OUTSIDE_REPOSITORY")
    selected = set(definitions) if "all" in areas or level == "L4" else set(areas)
    reasons = []
    for name in normalized:
        matches = {key for key, value in definitions.items()
                   if any(is_under(name, p) for p in value["sources"] + value["tests"])}
        if name.startswith("tests/fixtures/") or name in {"tests/conftest.py", "tests/suites.toml", "pyproject.toml", "uv.lock", "environment.yml"}:
            matches = set(definitions)
        if not matches:
            matches = set(definitions)
            reasons.append(f"未知依赖，扩大范围：{name}")
        selected |= matches
    if not selected and not l5:
        raise ValueError("TEST_SCOPE_REQUIRED")
    # 共享公共协议和运行边界的变化需要涵盖消费者；局部前端通过显式选择文件收窄。
    if selected & {"contracts", "runtime", "storage"}:
        selected |= {"core", "storage", "runtime", "workflows", "interfaces", "contracts"}
    records = inventory(root)["files"]
    python_paths = sorted({r["path"] for r in records if r["engine"] == "pytest" and selected.intersection(r["areas"])})
    frontend_paths = sorted({r["path"].removeprefix("product/frontend/") for r in records if r["engine"] == "vitest" and selected.intersection(r["areas"])})
    if normalized and selected == {"frontend"} and level in {"L1", "L2"}:
        local = []
        for name in normalized:
            if not name.startswith("product/frontend/src/features/"):
                local = []
                break
            feature = "/".join(name.split("/")[:5]).removeprefix("product/frontend/")
            local.extend(p for p in frontend_paths if is_under(p, feature))
        if local:
            frontend_paths = sorted(set(local))
    tasks = [{"id": "contracts", "command": "test", "args": ["tests/contracts", "-q"], "required": True}]
    if python_paths:
        tasks.append({"id": "collect", "command": "test", "args": [*python_paths, "--collect-only", "-qq"], "required": True})
    if level != "L1" and python_paths:
        markers = "not l5" if level in {"L3", "L4"} else "not (browser or process or slow or e2e or l5)"
        assigned = {p for p in python_paths if p.startswith("tests/contracts/")}
        # 每个文件只执行一次。通用 infra 分组只接收尚未被具体能力领取的文件。
        order = [name for name in definitions if name != "infrastructure"] + ["infrastructure"]
        for name in order:
            paths = [p for p in python_paths if p not in assigned and any(is_under(p, prefix) for prefix in definitions[name]["tests"])]
            if paths:
                assigned.update(paths)
                tasks.append({"id": "backend-" + name, "command": "test", "args": [*paths, "-m", markers, "-q", "--durations=15"], "required": True})
    if frontend_paths:
        tasks.append({"id": "frontend", "command": "frontend-test", "args": frontend_paths, "required": True})
    if level in {"L3", "L4"} and "frontend" in selected:
        tasks += [{"id": "build", "command": "prepare", "args": [], "required": True},
                  {"id": "browser-ui", "command": "verify", "args": ["browser"], "required": True}]
    if "docs" in selected or level == "L4":
        tasks += [{"id": "docs", "command": "docs", "args": [], "required": True}]
    if "contracts" in selected or level == "L4":
        tasks += [{"id": "schema", "command": "schema", "args": [], "required": True}]
    for suite in dict.fromkeys(l5):
        tasks.append({"id": "l5-" + suite, "command": "sample-test", "args": [suite], "required": True})
    files = source_files(root)
    for task in tasks:
        # 产品源码与共享夹具变化保守失效全部后端；文档、前端专属改动不使后端证据过期。
        if task["id"] == "backend-docs":
            inputs = files
        elif task["id"].startswith("backend-") or task["id"] in {"collect", "contracts"}:
            selected_files = test_dependencies(root, {p.split("::", 1)[0] for p in task["args"] if p.endswith(".py")})
            inputs = [p for p in files if not p.startswith(("docs/", "product/frontend/"))
                      and (not p.startswith("tests/") or p in selected_files or p.startswith(("tests/fixtures/", "tests/support/", "tests/contracts/", "tests/acceptance/")) or p in {"tests/conftest.py", "tests/suites.toml"})]
        elif task["id"] in {"frontend", "build", "browser-ui"}:
            inputs = [p for p in files if p.startswith(("product/frontend/", "product/backend/api/", "product/protocols/", "tests/acceptance/ui/", "tests/support/", "scripts/", "product/config/")) or p in {"pnpm-lock.yaml", "pyproject.toml", "uv.lock"}]
        else:
            inputs = files
        task["fingerprint"] = fingerprint(root, inputs)
    # 总指纹用于定位整个工作树；是否复用逐步骤检查实际输入，不能只比较 HEAD。
    return {"schema_version": "1", "level": level, "areas": sorted(selected), "changed": normalized,
            "reasons": reasons, "tasks": tasks, "fingerprint": fingerprint(root, files),
            "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
            "evidence_scope": "本地开发验证；L5 的每个子套件分别声明实际证明范围"}
