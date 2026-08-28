# =============================================================================
# Windows x64 Portable 发行组装
#
# 定位
#   dev.ps1 package 之下的唯一 Base Tree、双 ZIP 与校验和确定性构建器。
#
# 职责
#   复制可移动 Python/Chromium｜安装 frozen 依赖和 Wheel｜生成 launcher/release.json｜封装 full/nosamples。
#
# 边界
#   只写 var/development/release；不修改源码、uv.lock 或共享工具，不在 Portable 启动时安装或联网。
# =============================================================================

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path

from product.backend import __version__


RELEASE_VERSION = __version__
RELEASE_NAME = f"JieJian-WebV1-{RELEASE_VERSION}-Windows-x64"
FULL_ARCHIVE = f"{RELEASE_NAME}.zip"
NOSAMPLES_ARCHIVE = f"{RELEASE_NAME}-nosamples.zip"
_FORBIDDEN_PARTS = frozenset({".git", ".pytest_cache", "__pycache__", "node_modules", "tests"})
_TEXT_SUFFIXES = frozenset(
    {".cfg", ".cmd", ".ini", ".json", ".pth", ".ps1", ".py", ".toml", ".txt"}
)

_START_CMD = """@echo off\r
setlocal\r
set "JIEJIAN_RELEASE_ROOT=%~dp0"\r
"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%JIEJIAN_RELEASE_ROOT%runtime\\start.ps1" %*\r
set "JIEJIAN_EXIT_CODE=%ERRORLEVEL%"\r
endlocal & exit /b %JIEJIAN_EXIT_CODE%\r
"""

_START_PS1 = r'''# Windows x64 Portable 启动器：只解析包内运行时并进入正式 CLI serve，不执行安装、更新或构建。

[CmdletBinding()]
param([switch]$NoOpen)

$ErrorActionPreference = "Stop"
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$releasePath = Join-Path $PSScriptRoot "release.json"
$pythonRoot = Join-Path $PSScriptRoot "python"
$python = Join-Path $pythonRoot "python.exe"
$playwrightRoot = Join-Path $PSScriptRoot "playwright"
$frontend = Join-Path $pythonRoot "Lib\site-packages\product\frontend\dist"
$varDir = Join-Path $releaseRoot "var"
$temporary = Join-Path $varDir "temp"

if (-not (Test-Path -LiteralPath $releasePath -PathType Leaf)) { throw "Portable release.json 缺失" }
$release = Get-Content -LiteralPath $releasePath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$release.schema_version -ne "1" -or [string]$release.product -ne "JieJian Web V1" -or [string]$release.platform -ne "windows" -or [string]$release.architecture -ne "x64" -or [string]$release.runtime_layout_version -ne "1") { throw "Portable release.json 无效" }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Portable Python 缺失" }
if (-not (Test-Path -LiteralPath (Join-Path $frontend "index.html") -PathType Leaf)) { throw "Portable 前端缺失" }
if (-not (Test-Path -LiteralPath $playwrightRoot -PathType Container)) { throw "Portable Playwright 浏览器根缺失" }
$chromium = @(Get-ChildItem -LiteralPath $playwrightRoot -Recurse -Filter "chrome.exe" -File | Where-Object { $_.FullName -match "[\\/]chromium-[^\\/]+[\\/]chrome-win[^\\/]*[\\/]chrome\.exe$" })
if ($chromium.Count -ne 1) { throw "Portable Chromium 候选不唯一" }

New-Item -ItemType Directory -Path $temporary -Force | Out-Null
$env:JIEJIAN_PYTHON_EXECUTABLE = [IO.Path]::GetFullPath($python)
$env:JIEJIAN_PYTHON_ENVIRONMENT_PATH = [IO.Path]::GetFullPath($pythonRoot)
$env:JIEJIAN_PYTHON_ENVIRONMENT_TYPE = "uv-managed"
$env:JIEJIAN_RELEASE_ROOT = $releaseRoot
$env:JIEJIAN_RUNTIME_MODE = "portable"
$env:JIEJIAN_VAR_DIR = [IO.Path]::GetFullPath($varDir)
$env:JIEJIAN_FRONTEND_DIST = [IO.Path]::GetFullPath($frontend)
$env:JIEJIAN_PLAYWRIGHT_EXECUTABLE = [IO.Path]::GetFullPath($chromium[0].FullName)
$env:PLAYWRIGHT_BROWSERS_PATH = [IO.Path]::GetFullPath($playwrightRoot)
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONNOUSERSITE = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TEMP = [IO.Path]::GetFullPath($temporary)
$env:TMP = [IO.Path]::GetFullPath($temporary)
$env:PATH = "$pythonRoot;$env:SystemRoot\System32"
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:JIEJIAN_PROJECT_ROOT -ErrorAction SilentlyContinue
Remove-Item Env:JIEJIAN_RUNTIME_FINGERPRINT -ErrorAction SilentlyContinue
Set-Location -LiteralPath $varDir

$identityProbe = "from product.backend.infra.runtime.process.identity import python_environment_report; r=python_environment_report(); assert r['ok'], r['issues']; print(r['runtime_fingerprint'])"
$fingerprint = (& $python -B -c $identityProbe | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $fingerprint -notmatch "^[0-9a-f]{64}$") { throw "Portable Python 运行身份校验失败" }
$env:JIEJIAN_RUNTIME_FINGERPRINT = $fingerprint

$arguments = @("-B", "-m", "product.backend.cli", "--var-dir", $varDir, "serve", "--host", "127.0.0.1", "--port", "8765", "--frontend-dir", $frontend)
$sampleRoot = Join-Path $releaseRoot "samples\web\collaboration_space"
if (Test-Path -LiteralPath (Join-Path $sampleRoot "sample.json") -PathType Leaf) { $arguments += @("--official-sample-root", $sampleRoot) }
if ($NoOpen) { $arguments += "--no-open" } else { $arguments += "--open" }
& $python @arguments
exit $LASTEXITCODE
'''

_README = f"""界鉴 Web V1 {RELEASE_VERSION}（Windows x64 Portable）

启动：双击根目录 start.cmd。首次启动会在同目录创建 var，用于数据库、日志和运行证据。
本发行包已经包含 Python、产品依赖、前端和 Chromium；启动不需要安装 Conda、uv、Node、pnpm，也不会联网下载依赖。
请保持 runtime 目录完整。需要迁移时，在界鉴安全退出后整体移动或复制整个 {RELEASE_NAME} 目录。
完整版包含官方“协作空间”示例；nosamples 版不包含官方示例，但仍可接入你自己的本地 Web 应用。
"""


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="组装界鉴 Windows x64 Portable")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--python-source", type=Path, required=True)
    parser.add_argument("--playwright-source", type=Path, required=True)
    parser.add_argument("--samples-source", type=Path, required=True)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--uv-cache", type=Path, required=True)
    parser.add_argument("--toolchain", type=Path, required=True)
    return parser.parse_args()


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _reset_directory(path: Path, parent: Path) -> None:
    if path.resolve() == parent.resolve() or not _inside(path, parent):
        raise RuntimeError(f"拒绝清理发行根之外的路径: {path}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _run(
    arguments: Sequence[str | Path],
    *,
    cwd: Path,
    environment: dict[str, str],
    stream: bool = False,
) -> str:
    if stream:
        result = subprocess.run(
            [str(value) for value in arguments],
            cwd=cwd,
            env=environment,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"外部命令返回 {result.returncode}")
        return ""
    result = subprocess.run(
        [str(value) for value in arguments],
        cwd=cwd,
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        message = (result.stdout + result.stderr).strip()
        raise RuntimeError(message or f"外部命令返回 {result.returncode}")
    return result.stdout


def _runtime_environment(uv_cache: Path, temporary: Path) -> dict[str, str]:
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


def _copy_runtime(
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


def _install_product(
    *,
    project_root: Path,
    build_root: Path,
    python: Path,
    wheel: Path,
    uv: Path,
    environment: dict[str, str],
) -> None:
    requirements = build_root / "portable-runtime-requirements.txt"
    _run(
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
    _run(
        (*common, "--requirements", requirements),
        cwd=project_root,
        environment=environment,
        stream=True,
    )
    _run((*common, "--no-deps", wheel), cwd=project_root, environment=environment, stream=True)
    _prune_installed_runtime(python)


def _prune_installed_runtime(python: Path) -> None:
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


def _metadata(python: Path, playwright_root: Path, environment: dict[str, str]) -> dict[str, str]:
    probe = (
        "import importlib.metadata,json,platform;"
        "print(json.dumps({'python':platform.python_version(),"
        "'jiejian':importlib.metadata.version('jiejian'),"
        "'playwright':importlib.metadata.version('playwright')}))"
    )
    values = json.loads(
        _run((python, "-B", "-c", probe), cwd=python.parent, environment=environment)
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


def _write_runtime_files(base: Path, metadata: dict[str, str]) -> None:
    (base / "start.cmd").write_bytes(_START_CMD.encode("ascii"))
    (base / "README.txt").write_bytes(b"\xef\xbb\xbf" + _README.encode("utf-8"))
    runtime = base / "runtime"
    (runtime / "start.ps1").write_bytes(
        b"\xef\xbb\xbf" + _START_PS1.replace("\n", "\r\n").encode("utf-8")
    )
    release = {
        "schema_version": "1",
        "product": "JieJian Web V1",
        "version": RELEASE_VERSION,
        "package_version": metadata["wheel_version"],
        "platform": "windows",
        "architecture": "x64",
        "runtime_layout_version": "1",
        "python_version": metadata["python_version"],
        "playwright_version": metadata["playwright_version"],
        "chromium_revision": metadata["chromium_revision"],
    }
    (runtime / "release.json").write_text(
        json.dumps(release, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _portable_environment(base: Path, python: Path, playwright_root: Path) -> dict[str, str]:
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
                (python.parent / "Lib" / "site-packages" / "product" / "frontend" / "dist").resolve()
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


def _validate_tree_content(base: Path, project_root: Path) -> None:
    """拒绝 Base Tree 中的源码仓库路径、缓存和本地 Wheel 来源元数据。"""

    repository_markers = {
        str(project_root.resolve()),
        str(project_root.resolve()).replace("\\", "/"),
    }
    for path in base.rglob("*"):
        if any(part.casefold() in _FORBIDDEN_PARTS for part in path.parts) or path.suffix.lower() in {".pyc", ".pyo"}:
            raise RuntimeError(f"Portable Tree 含禁止生成物: {path.relative_to(base)}")
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if any(marker in text for marker in repository_markers):
            raise RuntimeError(f"Portable Tree 泄漏构建仓库绝对路径: {path.relative_to(base)}")
    site_packages = base / "runtime" / "python" / "Lib" / "site-packages"
    if tuple(site_packages.glob("jiejian-*.dist-info/direct_url.json")):
        raise RuntimeError("Portable Tree 仍包含构建 Wheel 的 direct_url 元数据")


def _validate_base(base: Path, project_root: Path) -> None:
    python = base / "runtime" / "python" / "python.exe"
    playwright_root = base / "runtime" / "playwright"
    frontend = python.parent / "Lib" / "site-packages" / "product" / "frontend" / "dist" / "index.html"
    required = (
        base / "start.cmd",
        base / "README.txt",
        base / "runtime" / "start.ps1",
        base / "runtime" / "release.json",
        python,
        frontend,
    )
    if not all(path.is_file() for path in required):
        raise RuntimeError("Base Portable Tree 缺少必需文件")
    if set(path.name for path in base.iterdir()) != {"README.txt", "runtime", "start.cmd"}:
        raise RuntimeError("Base Portable Tree 根目录包含职责外文件")
    environment = _portable_environment(base, python, playwright_root)
    probe = (
        "import json; from pathlib import Path;"
        "from product.backend.infra.runtime.process.identity import python_environment_report;"
        "r=python_environment_report(); root=Path(r['release_root']);"
        "assert r['ok'], r['issues'];"
        "assert all(Path(v).resolve().is_relative_to(root) for v in r['package_origins'].values() if v);"
        "print(json.dumps({'fingerprint':r['runtime_fingerprint'],'product':r['package_origins']['product']}))"
    )
    _run((python, "-B", "-c", probe), cwd=base / "var", environment=environment)
    shutil.rmtree(base / "var")
    _validate_tree_content(base, project_root)


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        if any(part.casefold() in _FORBIDDEN_PARTS for part in path.parts) or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        yield path


def _write_zip(destination: Path, base: Path, samples: Path | None) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            entries: list[tuple[Path, Path]] = [
                (path, Path(RELEASE_NAME) / path.relative_to(base)) for path in _iter_files(base)
            ]
            if samples is not None:
                entries.extend(
                    (path, Path(RELEASE_NAME) / "samples" / path.relative_to(samples))
                    for path in _iter_files(samples)
                )
            for source, relative in sorted(entries, key=lambda pair: pair[1].as_posix()):
                info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _archive_content(path: Path, *, without_samples: bool) -> dict[str, str]:
    with zipfile.ZipFile(path) as archive:
        content: dict[str, str] = {}
        for info in archive.infolist():
            relative = Path(info.filename)
            if relative.parts[0] != RELEASE_NAME or relative.is_absolute():
                raise RuntimeError(f"Portable ZIP 根目录无效: {info.filename}")
            if len(relative.parts) > 1 and relative.parts[1] == "samples":
                if without_samples:
                    raise RuntimeError("nosamples ZIP 意外包含 samples")
                continue
            content[relative.as_posix()] = hashlib.sha256(archive.read(info)).hexdigest()
        return content


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _progress(step: int, message: str) -> None:
    """输出稳定阶段而非逐文件噪声，并立即刷新给外层 PowerShell。"""

    print(f"[{step}/6] {message}", flush=True)


def build(arguments: argparse.Namespace) -> None:
    project_root = arguments.project_root.resolve()
    release_root = arguments.release_root.resolve()
    build_root = release_root / "build"
    artifacts = release_root / "artifacts"
    for path in (
        arguments.wheel,
        arguments.python_source / "python.exe",
        arguments.uv,
        arguments.toolchain,
        arguments.samples_source / "web" / "collaboration_space" / "sample.json",
    ):
        if not path.resolve().is_file():
            raise RuntimeError(f"Portable 构建输入缺失: {path}")
    if not arguments.playwright_source.resolve().is_dir():
        raise RuntimeError("Portable Playwright 构建输入缺失")
    if not _inside(release_root, project_root / "var" / "development"):
        raise RuntimeError("Portable release root 必须位于 var/development")
    toolchain = json.loads(arguments.toolchain.read_text(encoding="utf-8"))
    if (
        toolchain["python"].get("release_version") != "3.13.13"
        or toolchain["python"].get("release_distribution")
        != "cpython-3.13.13-windows-x86_64-none"
    ):
        raise RuntimeError("Portable Python 来源未冻结为已验证发行版")

    base_parent = build_root / "base"
    _reset_directory(base_parent, build_root)
    base = base_parent / RELEASE_NAME
    base.mkdir()
    artifacts.mkdir(parents=True, exist_ok=True)
    environment = _runtime_environment(arguments.uv_cache, build_root / "temp")
    _progress(1, "复制固定 CPython 与 Playwright 运行时")
    python, playwright_root = _copy_runtime(
        base,
        python_source=arguments.python_source.resolve(),
        playwright_source=arguments.playwright_source.resolve(),
    )
    _progress(2, "安装 frozen 生产依赖与内部 Wheel")
    _install_product(
        project_root=project_root,
        build_root=build_root,
        python=python,
        wheel=arguments.wheel.resolve(),
        uv=arguments.uv.resolve(),
        environment=environment,
    )
    _progress(3, "生成元数据并校验唯一 Base Tree")
    metadata = _metadata(python, playwright_root, environment)
    if metadata["wheel_version"] != RELEASE_VERSION:
        raise RuntimeError(
            "Portable Wheel 版本与产品版本真源不一致: "
            f"expected={RELEASE_VERSION} actual={metadata['wheel_version']}"
        )
    _write_runtime_files(base, metadata)
    _validate_base(base, project_root)

    full = artifacts / FULL_ARCHIVE
    nosamples = artifacts / NOSAMPLES_ARCHIVE
    _progress(4, "生成包含官方 Sample 的 full ZIP")
    _write_zip(full, base, arguments.samples_source.resolve())
    _progress(5, "生成不包含 Sample 的 nosamples ZIP")
    _write_zip(nosamples, base, None)
    _progress(6, "核对双包产品树并写入 SHA256")
    if _archive_content(full, without_samples=False) != _archive_content(
        nosamples, without_samples=True
    ):
        raise RuntimeError("full 与 nosamples 的产品文件不一致")
    sums = artifacts / "SHA256SUMS.txt"
    sums.write_text(
        f"{_sha256(full)}  {full.name}\n{_sha256(nosamples)}  {nosamples.name}\n",
        encoding="ascii",
    )
    print(f"PORTABLE_FULL={full}")
    print(f"PORTABLE_NOSAMPLES={nosamples}")
    print(f"PORTABLE_SHA256={sums}")


def main() -> None:
    try:
        build(_arguments())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Portable 构建失败：{exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
