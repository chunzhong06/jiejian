# 组装固定运行环境、安装同一产品并建立包内导入身份。
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from scripts.build.common import run


def runtime_environment(uv_cache: Path, temporary: Path) -> dict[str, str]:
    temporary.mkdir(parents=True, exist_ok=True)
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in {"COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR"}
    }
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "TEMP": str(temporary.resolve()),
            "TMP": str(temporary.resolve()),
            "UV_CACHE_DIR": str(uv_cache.resolve()),
        }
    )
    return environment


def copy_runtime(
    base: Path,
    *,
    python_source: Path,
    playwright_source: Path,
) -> tuple[Path, Path]:
    runtime = base / "runtime"
    runtime.mkdir(parents=True)
    python = runtime / "python"
    playwright = runtime / "playwright"
    shutil.copytree(python_source, python)
    shutil.copytree(playwright_source, playwright)
    return python / "python.exe", playwright


def install_product(
    *,
    project_root: Path,
    build_root: Path,
    python: Path,
    wheel: Path,
    uv: Path,
    environment: dict[str, str],
) -> None:
    requirements = build_root / "portable-runtime-requirements.txt"
    run(
        (
            uv,
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "requirements.txt",
            "--output-file",
            requirements,
        ),
        cwd=project_root,
        environment=environment,
    )
    common = (uv, "pip", "install", "--python", python, "--system", "--break-system-packages")
    run(
        (*common, "--requirements", requirements),
        cwd=project_root,
        environment=environment,
        stream=True,
    )
    run((*common, "--no-deps", wheel), cwd=project_root, environment=environment, stream=True)
    prune_installed_runtime(python)


def prune_installed_runtime(python: Path) -> None:
    """删除 Wheel 安装带入但发行运行不需要的测试与 Python 生成物。"""

    site_packages = python.parent / "Lib" / "site-packages"
    for direct_url in site_packages.glob("jiejian-*.dist-info/direct_url.json"):
        direct_url.unlink()
    for tests in sorted(
        (
            path
            for path in python.parent.rglob("*")
            if path.is_dir() and path.name.casefold() == "tests"
        ),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        shutil.rmtree(tests)
    for cache in sorted(python.parent.rglob("__pycache__"), reverse=True):
        shutil.rmtree(cache)
    for bytecode in python.parent.rglob("*.py[co]"):
        bytecode.unlink()


def metadata(python: Path, playwright_root: Path, environment: dict[str, str]) -> dict[str, str]:
    probe = (
        "import importlib.metadata,json,platform;"
        "print(json.dumps({'python':platform.python_version(),"
        "'jiejian':importlib.metadata.version('jiejian'),"
        "'playwright':importlib.metadata.version('playwright')}))"
    )
    values = json.loads(
        run((python, "-B", "-c", probe), cwd=python.parent, environment=environment)
    )
    candidates = sorted(
        path.name.removeprefix("chromium-")
        for path in playwright_root.glob("chromium-*")
        if path.is_dir()
    )
    if len(candidates) != 1:
        raise RuntimeError("Portable Chromium revision 候选不唯一")
    return {
        "python_version": str(values["python"]),
        "wheel_version": str(values["jiejian"]),
        "playwright_version": str(values["playwright"]),
        "chromium_revision": candidates[0],
    }


def place_product(base: Path, python: Path) -> None:
    """移动已安装的同一 Wheel；相对 .pth 让主进程和全部子进程导入同一 app，不使用 PYTHONPATH。"""
    site_packages = python.parent / 'Lib' / 'site-packages'
    distributions = tuple(site_packages.glob('jiejian-*.dist-info'))
    if len(distributions) != 1 or not (site_packages / 'product').is_dir():
        raise RuntimeError('Portable 必须包含唯一已安装产品')
    app = base / 'app'
    app.mkdir()
    for path in (site_packages / 'product', distributions[0]):
        shutil.move(str(path), app / path.name)
    (site_packages / 'jiejian-app.pth').write_text('../../../../app\n', encoding='ascii')
    # Wheel console-script 带有构建时解释器路径；便携入口始终用包内 python -m，不交付这个失效副本。
    for name in ('jiejian.exe', 'jiejian-script.py'):
        (python.parent / 'Scripts' / name).unlink(missing_ok=True)


def portable_environment(base: Path, python: Path, playwright_root: Path) -> dict[str, str]:
    chromium = tuple(
        path
        for path in playwright_root.rglob("chrome.exe")
        if "chromium-" in path.as_posix() and "chrome-win" in path.as_posix()
    )
    if len(chromium) != 1:
        raise RuntimeError("Portable Chromium 可执行文件候选不唯一")
    temporary = base / "var" / "temp"
    temporary.mkdir(parents=True)
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR", "")
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in {"COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR"}
    }
    environment.update(
        {
            "JIEJIAN_PYTHON_EXECUTABLE": str(python.resolve()),
            "JIEJIAN_PYTHON_ENVIRONMENT_PATH": str(python.parent.resolve()),
            "JIEJIAN_PYTHON_ENVIRONMENT_TYPE": "uv-managed",
            "JIEJIAN_RELEASE_ROOT": str(base.resolve()),
            "JIEJIAN_RUNTIME_MODE": "portable",
            "JIEJIAN_VAR_DIR": str((base / "var").resolve()),
            "JIEJIAN_FRONTEND_DIST": str(
                (base / "app" / "product" / "frontend" / "dist").resolve()
            ),
            "JIEJIAN_PLAYWRIGHT_EXECUTABLE": str(chromium[0].resolve()),
            "PLAYWRIGHT_BROWSERS_PATH": str(playwright_root.resolve()),
            "PATH": os.pathsep.join(
                part for part in (str(python.parent.resolve()), str(Path(system_root) / "System32")) if part
            ),
            "TEMP": str(temporary.resolve()),
            "TMP": str(temporary.resolve()),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return environment
