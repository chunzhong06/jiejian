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
from product.protocols.runtime.portable_release import PortableReleaseManifest


RELEASE_VERSION = __version__
RELEASE_NAME = f"JieJian-WebV1-{RELEASE_VERSION}-Windows-x64"
FULL_ARCHIVE = f"{RELEASE_NAME}.zip"
NOSAMPLES_ARCHIVE = f"{RELEASE_NAME}-nosamples.zip"
_FORBIDDEN_PARTS = frozenset({".git", ".pytest_cache", "__pycache__", "node_modules", "tests"})
_TEXT_SUFFIXES = frozenset(
    {".cfg", ".cmd", ".ini", ".json", ".pth", ".ps1", ".py", ".toml", ".txt"}
)

_START_PS1 = Path(__file__).with_name('portable_start.ps1').read_text(encoding='utf-8-sig')
_USER_GUIDE = Path(__file__).with_name('portable_guide.txt').read_text(encoding='utf-8')

_README = f"""界鉴 {RELEASE_VERSION}（Windows x64 便携版）

启动：完整解压后双击“界鉴.exe”。所有程序已在发布前构建，启动不会安装依赖、下载或重新编译。
重复双击会回到正在运行的界面。关闭界面窗口后也可双击恢复；安全退出请使用界面“设置”中的退出入口。
app 为固定产品，runtime 为固定运行环境，samples 为唯一示例模板，docs 为使用说明与许可。
var 保存项目、检查证据、设置与运行数据。它在首次启动时建立，请保留并定期备份。
更新：安全退出后更换完整程序组件，保留 var。换电脑需要重新登录，Windows 凭据不会随文件夹迁移。
完整版提供数字展馆官方示例；nosamples 版适用于只接入自己应用的用户。
详细使用、更新与问题处理见 docs/使用说明.txt；启动阶段日志在 var/logs/launcher.log。
"""



def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="组装界鉴 Windows x64 Portable")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--release-root", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--python-source", type=Path, required=True)
    parser.add_argument("--playwright-source", type=Path, required=True)
    parser.add_argument("--node-executable", type=Path, required=True)
    parser.add_argument("--launcher-compiler", type=Path, required=True)
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


def _place_product(base: Path, python: Path) -> None:
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


def _launcher_icon(base: Path, environment: dict[str, str]) -> Path:
    """将网页现用矢量标志转为多尺寸ICO；离线生成物只进入本次构建目录。"""
    import re
    import struct
    from playwright.sync_api import sync_playwright
    header = Path(__file__).parents[2] / 'product/frontend/src/app/shell/AppHeader.tsx'
    markup = header.read_text(encoding='utf-8')
    mark = re.search(r'<button className="product-brand".*?(<svg\b.*?</svg>)', markup, re.S)
    if mark is None:
        raise RuntimeError('网页品牌标志缺失，拒绝生成替代图标')
    browsers = [p for p in (base / 'runtime/playwright').rglob('chrome.exe') if 'chromium-' in p.as_posix()]
    if len(browsers) != 1:
        raise RuntimeError('构建图标需要包内唯一Chromium')
    pictures = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(browsers[0]), headless=True, env=environment)
        try:
            page = browser.new_page(offline=True)
            svg = mark[1].replace('strokeWidth=', 'stroke-width=').replace('strokeLinejoin=', 'stroke-linejoin=')
            page.set_content('<style>html,body{margin:0;background:transparent}svg{width:100vw;height:100vh;color:rgb(186,196,249)}</style>' + svg)
            for size in (16, 24, 32, 48, 64, 128, 256):
                page.set_viewport_size({'width': size, 'height': size})
                pictures.append((size, page.screenshot(omit_background=True)))
        finally:
            browser.close()
    offset = 6 + 16 * len(pictures)
    records = []
    for size, picture in pictures:
        records.append(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(picture), offset))
        offset += len(picture)
    icon = base.parent / 'jiejian.ico'
    icon.write_bytes(struct.pack('<HHH', 0, 1, len(pictures)) + b''.join(records) + b''.join(p[1] for p in pictures))
    (base.parent / 'jiejian-icon-preview.png').write_bytes(pictures[-1][1])
    return icon


def _compile_launcher(base: Path, compiler: Path, toolchain: dict, environment: dict[str, str]) -> None:
    """构建一次 Win32 薄入口，运行时仅依赖 Windows 自带 DLL。"""
    import re
    source = Path(__file__).with_name('launcher.c')
    # 与源码启动面板共用字形和配色，生成头只留在构建目录；版本始终来自产品真源。
    panel = source.parent.parent.joinpath('startup/panel.ps1').read_text(encoding='utf-8-sig')
    art = re.search(r'StartupPanelArt = @\((.*?)\n\)', panel, re.S)
    colors = re.search(r'StartupPanelArtColors = @\((.*?)\)', panel)
    if art is None or colors is None:
        raise RuntimeError('启动艺术字或配色定义缺失')
    rows = re.findall(r'"([^"\n]+)"', art[1])
    palette = re.findall(r'"(\d+);(\d+);(\d+)"', colors[1])
    if len(rows) != 6 or len(palette) != len(rows):
        raise RuntimeError('启动艺术字与渐变行数不一致')
    header = base.parent / 'startup-brand.h'
    header.write_text('/* 构建时读取现有启动面板；不得手工编辑。 */\n'
        + 'static const wchar_t *brand_version = L' + json.dumps(RELEASE_VERSION) + ';\n'
        + 'static const wchar_t *brand_art[] = {' + ','.join('L' + json.dumps(row) for row in rows) + '};\n'
        + 'static const COLORREF brand_colors[] = {' + ','.join('RGB('+','.join(color)+')' for color in palette) + '};\n', encoding='utf-8')
    env = {**environment, 'PATH': os.pathsep.join((str(compiler.parent), str(Path(os.environ['SYSTEMROOT']) / 'System32')))}
    config = toolchain['launcher']
    target = _run((compiler, '-dumpmachine'), cwd=base, environment=env).strip()
    version = _run((compiler, '-dumpfullversion'), cwd=base, environment=env).strip()
    if target != config['target'] or version != config['version']:
        raise RuntimeError('启动器编译器与 toolchain.json 的版本或目标不一致')
    icon = _launcher_icon(base, environment)
    resource = base.parent / 'startup-icon.rc'
    resource.write_text('#pragma code_page(65001)\n1 ICON "' + icon.as_posix() + '"\n', encoding='utf-8')
    resource_object = base.parent / 'startup-icon.o'
    windres = Path(_run((compiler, '-print-prog-name=windres'), cwd=base, environment=env).strip())
    if not windres.is_absolute() or not windres.is_file():
        raise RuntimeError('启动器工具链缺少可定位的 windres')
    _run((windres, '--codepage=65001', '-i', resource, '-o', resource_object), cwd=base, environment=env)
    _run((compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-municode', '-mwindows',
          '-static-libgcc', '-s', '-Wl,--no-insert-timestamp', '-finput-charset=UTF-8',
          '-I', base.parent, source, resource_object, '-o', base / '界鉴.exe', '-lshell32', '-luser32', '-lgdi32'), cwd=base, environment=env)
    objdump = Path(_run((compiler, '-print-prog-name=objdump'), cwd=base, environment=env).strip())
    if not objdump.is_absolute() or not objdump.is_file():
        raise RuntimeError('启动器工具链缺少可定位的 objdump')
    imports = _run((objdump, '-p', base / '界鉴.exe'), cwd=base, environment=env)
    names = {name.casefold() for name in re.findall(r'DLL Name:\s*(\S+)', imports)}
    if not names or any(name not in {'kernel32.dll', 'msvcrt.dll', 'ucrtbase.dll', 'user32.dll', 'shell32.dll', 'gdi32.dll', 'advapi32.dll'} and not name.startswith('api-ms-win-crt-') for name in names):
        raise RuntimeError('原生入口依赖了非 Windows 系统 DLL')


def _write_runtime_files(base: Path, metadata: dict[str, str]) -> None:
    (base / "README.txt").write_bytes(b"\xef\xbb\xbf" + _README.encode("utf-8"))
    app = base / "app"
    app.mkdir(exist_ok=True)
    (app / "start.ps1").write_bytes(
        b"\xef\xbb\xbf" + _START_PS1.replace("\n", "\r\n").encode("utf-8")
    )
    release = {
        "schema_version": "3",
        "product": "JieJian Web V1",
        "version": RELEASE_VERSION,
        "package_version": metadata["wheel_version"],
        "platform": "windows",
        "architecture": "x64",
        "runtime_layout_version": "3",
        "python_version": metadata["python_version"],
        "playwright_version": metadata["playwright_version"],
        "chromium_revision": metadata["chromium_revision"],
        "node_version": metadata["node_version"],
        "node_sha256": metadata["node_sha256"],
    }
    release = PortableReleaseManifest.model_validate(release).model_dump(mode='json')
    (app / "release.json").write_text(
        json.dumps(release, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    docs = base / 'docs'
    docs.mkdir(exist_ok=True)
    docs.joinpath('使用说明.txt').write_text(_README + '\n' + _USER_GUIDE, encoding='utf-8-sig')
    docs.joinpath('版本说明.txt').write_text(f'界鉴 {RELEASE_VERSION}\n\n本版本包含本地 Web 应用接入、规则审阅、材料准备、权限检查、原题复验与统一历史。\n程序在发布前构建；根目录的界鉴.exe是日常入口。\n', encoding='utf-8-sig')
    docs.joinpath('第三方许可.txt').write_text('第三方许可证随对应固定组件保留：\nPython：runtime/python 中的 LICENSE 文件。\nNode：runtime/node/LICENSE.txt。\nChromium：runtime/playwright 中各组件的 LICENSE、LICENSES 和 credits 文件。\nPython 依赖：runtime/python/Lib/site-packages 下各 *.dist-info 的 licenses、LICENSE 或 COPYING。\nMiSans 字体：app/product/frontend/dist/assets 中的 MiSans-LICENSE PDF。\n原生启动器：本目录保留 MinGW-w64-COPYING、MinGW-w64-NOTICES、GCC-GPL-3.0、GCC-Runtime-Exception-3.1 与 Conda-forge-GCC-COPYING；来源见 SOURCES.txt。\n', encoding='utf-8-sig')
    for license_file in Path(__file__).with_name('licenses').glob('*.txt'):
        shutil.copyfile(license_file, docs / license_file.name)


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
    if tuple(base.rglob("jiejian-*.dist-info/direct_url.json")):
        raise RuntimeError("Portable Tree 仍包含构建 Wheel 的 direct_url 元数据")


def _validate_base(base: Path, project_root: Path) -> None:
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
    environment = _portable_environment(base, python, playwright_root)
    probe = (
        "import json; from pathlib import Path;"
        "from product.backend.infra.runtime.process.controlled.identity import python_environment_report;"
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
        arguments.node_executable,
        arguments.launcher_compiler,
        arguments.python_source / "python.exe",
        arguments.uv,
        arguments.toolchain,
        arguments.samples_source / "digital_gallery" / "sample.json",
    ):
        if not path.resolve().is_file():
            raise RuntimeError(f"Portable 构建输入缺失: {path}")
    if not arguments.playwright_source.resolve().is_dir():
        raise RuntimeError("Portable Playwright 构建输入缺失")
    if not _inside(arguments.node_executable, project_root / 'var' / 'development' / 'tools' / 'node'):
        raise RuntimeError('Portable Node 必须来自已固定的构建工具目录')
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
    node_root = base / 'runtime' / 'node'
    node_root.mkdir()
    shutil.copyfile(arguments.node_executable, node_root / 'node.exe')
    license_path = arguments.node_executable.parent / 'LICENSE'
    if license_path.is_file():
        shutil.copyfile(license_path,node_root / 'LICENSE.txt')
    node_version = _run((node_root / 'node.exe','--version'),cwd=base,environment=environment).strip().removeprefix('v')
    if node_version != toolchain['node']['build_version']:
        raise RuntimeError('Portable Node 版本与冻结工具链不一致')
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
    metadata.update(node_version=node_version,node_sha256=_sha256(node_root / 'node.exe'))
    if metadata["wheel_version"] != RELEASE_VERSION:
        raise RuntimeError(
            "Portable Wheel 版本与产品版本真源不一致: "
            f"expected={RELEASE_VERSION} actual={metadata['wheel_version']}"
        )
    _place_product(base, python)
    _write_runtime_files(base, metadata)
    _compile_launcher(base, arguments.launcher_compiler.resolve(), toolchain, environment)
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
