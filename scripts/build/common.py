# 构建进程、受限目录和内容摘要；不在导入时读取发行资源。
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from product.backend import __version__

RELEASE_VERSION = __version__
RELEASE_NAME = f"JieJian-WebV1-{RELEASE_VERSION}-Windows-x64"
FULL_ARCHIVE = f"{RELEASE_NAME}.zip"
NOSAMPLES_ARCHIVE = f"{RELEASE_NAME}-nosamples.zip"
FORBIDDEN_PARTS = frozenset({".git", ".pytest_cache", "__pycache__", "node_modules", "tests"})
TEXT_SUFFIXES = frozenset({".cfg", ".cmd", ".ini", ".json", ".pth", ".ps1", ".py", ".toml", ".txt"})


def excluded_from_release(relative: Path, *, allow_node_npm: bool = False) -> bool:
    parts = relative.parts
    # 唯一例外是固定 Node 自带 npm；样例和其他目录不能借此带入项目依赖。
    npm = allow_node_npm and (parts == ('runtime', 'node', 'node_modules') or parts[:4] == ('runtime', 'node', 'node_modules', 'npm'))
    forbidden = FORBIDDEN_PARTS - {'node_modules'} if npm else FORBIDDEN_PARTS
    return any(part.casefold() in forbidden for part in parts) or relative.suffix.lower() in {'.pyc', '.pyo'}


def inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def reset_directory(path: Path, parent: Path) -> None:
    if path.resolve() == parent.resolve() or not inside(path, parent):
        raise RuntimeError(f"拒绝清理发行根之外的路径: {path}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def run(
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
