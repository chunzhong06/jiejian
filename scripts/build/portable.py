# 发行总入口只协调固定输入、运行环境组装、校验与归档发布。
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from scripts.build.common import RELEASE_VERSION, RELEASE_NAME, FULL_ARCHIVE, NOSAMPLES_ARCHIVE, inside, reset_directory, run, sha256
from scripts.build.runtime import runtime_environment, copy_runtime, install_product, metadata, place_product
from scripts.build.resources import write_runtime_files
from scripts.build.launcher import compile_launcher
from scripts.build.validation import validate_base
from scripts.build.archive import write_zip, archive_content


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
    if not inside(arguments.node_executable, project_root / 'var' / 'development' / 'tools' / 'node'):
        raise RuntimeError('Portable Node 必须来自已固定的构建工具目录')
    if not inside(release_root, project_root / "var" / "development"):
        raise RuntimeError("Portable release root 必须位于 var/development")
    toolchain = json.loads(arguments.toolchain.read_text(encoding="utf-8"))
    if (
        toolchain["python"].get("release_version") != "3.13.13"
        or toolchain["python"].get("release_distribution")
        != "cpython-3.13.13-windows-x86_64-none"
    ):
        raise RuntimeError("Portable Python 来源未冻结为已验证发行版")

    base_parent = build_root / "base"
    reset_directory(base_parent, build_root)
    base = base_parent / RELEASE_NAME
    base.mkdir()
    artifacts.mkdir(parents=True, exist_ok=True)
    environment = runtime_environment(arguments.uv_cache, build_root / "temp")
    _progress(1, "复制固定 CPython 与 Playwright 运行时")
    python, playwright_root = copy_runtime(
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
    node_version = run((node_root / 'node.exe','--version'),cwd=base,environment=environment).strip().removeprefix('v')
    if node_version != toolchain['node']['build_version']:
        raise RuntimeError('Portable Node 版本与冻结工具链不一致')
    _progress(2, "安装 frozen 生产依赖与内部 Wheel")
    install_product(
        project_root=project_root,
        build_root=build_root,
        python=python,
        wheel=arguments.wheel.resolve(),
        uv=arguments.uv.resolve(),
        environment=environment,
    )
    _progress(3, "生成元数据并校验唯一 Base Tree")
    runtime_metadata = metadata(python, playwright_root, environment)
    runtime_metadata.update(node_version=node_version,node_sha256=sha256(node_root / 'node.exe'))
    if runtime_metadata["wheel_version"] != RELEASE_VERSION:
        raise RuntimeError(
            "Portable Wheel 版本与产品版本真源不一致: "
            f"expected={RELEASE_VERSION} actual={runtime_metadata['wheel_version']}"
        )
    place_product(base, python)
    write_runtime_files(base, runtime_metadata, project_root)
    compile_launcher(base, arguments.launcher_compiler.resolve(), toolchain, environment, project_root)
    validate_base(base, project_root)

    full = artifacts / FULL_ARCHIVE
    nosamples = artifacts / NOSAMPLES_ARCHIVE
    _progress(4, "生成包含官方 Sample 的 full ZIP")
    write_zip(full, base, arguments.samples_source.resolve())
    _progress(5, "生成不包含 Sample 的 nosamples ZIP")
    write_zip(nosamples, base, None)
    _progress(6, "核对双包产品树并写入 SHA256")
    if archive_content(full, without_samples=False) != archive_content(
        nosamples, without_samples=True
    ):
        raise RuntimeError("full 与 nosamples 的产品文件不一致")
    sums = artifacts / "SHA256SUMS.txt"
    sums.write_text(
        f"{sha256(full)}  {full.name}\n{sha256(nosamples)}  {nosamples.name}\n",
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
