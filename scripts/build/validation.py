# 核验发行文件组成、包内运行身份及构建来源泄漏。
from __future__ import annotations

import shutil
from pathlib import Path
from scripts.build.common import FORBIDDEN_PARTS, TEXT_SUFFIXES, run
from scripts.build.runtime import portable_environment


def validate_tree_content(base: Path, project_root: Path) -> None:
    """拒绝 Base Tree 中的源码仓库路径、缓存和本地 Wheel 来源元数据。"""

    repository_markers = {
        str(project_root.resolve()),
        str(project_root.resolve()).replace("\\", "/"),
    }
    for path in base.rglob("*"):
        if any(part.casefold() in FORBIDDEN_PARTS for part in path.parts) or path.suffix.lower() in {".pyc", ".pyo"}:
            raise RuntimeError(f"Portable Tree 含禁止生成物: {path.relative_to(base)}")
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if any(marker in text for marker in repository_markers):
            raise RuntimeError(f"Portable Tree 泄漏构建仓库绝对路径: {path.relative_to(base)}")
    if tuple(base.rglob("jiejian-*.dist-info/direct_url.json")):
        raise RuntimeError("Portable Tree 仍包含构建 Wheel 的 direct_url 元数据")


def validate_base(base: Path, project_root: Path) -> None:
    python = base / "runtime" / "python" / "python.exe"
    playwright_root = base / "runtime" / "playwright"
    frontend = base / "app" / "product" / "frontend" / "dist" / "index.html"
    required = (
        base / "界鉴.exe",
        base / "README.txt",
        base / "app" / "start.ps1",
        base / "app" / "release.json",
        base / "docs" / "使用说明.txt",
        python,
        frontend,
        base / "runtime" / "node" / "node.exe",
    )
    if not all(path.is_file() for path in required):
        raise RuntimeError("Base Portable Tree 缺少必需文件")
    if set(path.name for path in base.iterdir()) != {"README.txt", "runtime", "app", "docs", "界鉴.exe"}:
        raise RuntimeError("Base Portable Tree 根目录包含职责外文件")
    environment = portable_environment(base, python, playwright_root)
    probe = (
        "import json; from pathlib import Path;"
        "from product.backend.infrastructure.runtime.process.controlled.identity import python_environment_report;"
        "r=python_environment_report(); root=Path(r['release_root']);"
        "assert r['ok'], r['issues'];"
        "assert all(Path(v).resolve().is_relative_to(root) for v in r['package_origins'].values() if v);"
        "print(json.dumps({'fingerprint':r['runtime_fingerprint'],'product':r['package_origins']['product']}))"
    )
    run((python, "-B", "-c", probe), cwd=base / "var", environment=environment)
    shutil.rmtree(base / "var")
    validate_tree_content(base, project_root)
