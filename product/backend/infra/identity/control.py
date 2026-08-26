# =============================================================================
# 测试身份准备控制标记
#
# 定位
#   控制面与独立 headed browser 进程之间的无秘密本地控制事实。
#
# 职责
#   固定 ready/save/cancel 标记｜原子写入｜校验路径和固定内容。
#
# 边界
#   不保存用户输入、登录状态或秘密；每个目录只属于一个随机 preparation id。
#
# 调用链
#   IdentityPreparationManager ↔ control markers ↔ identity_preparation_process
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError


_MARKERS = {"browser.ready", "login.save", "preparation.cancel"}


@dataclass(frozen=True, slots=True)
class IdentityPreparationControlPaths:
    root: Path
    ready: Path
    save: Path
    cancel: Path
    journal: Path


def identity_preparation_control_paths(root: Path) -> IdentityPreparationControlPaths:
    resolved = root.resolve()
    if not resolved.is_dir():
        raise JiejianError(
            ErrorCode.IDENTITY_PREPARATION_FAILED,
            "测试账号准备目录尚未就绪",
        )
    return IdentityPreparationControlPaths(
        root=resolved,
        ready=resolved / "browser.ready",
        save=resolved / "login.save",
        cancel=resolved / "preparation.cancel",
        journal=resolved / "secret-refs.json",
    )


def write_identity_preparation_marker(path: Path, *, root: Path) -> bool:
    resolved_root = root.resolve()
    target = path.resolve()
    if target.parent != resolved_root or target.name not in _MARKERS:
        raise JiejianError(
            ErrorCode.IDENTITY_PREPARATION_FAILED,
            "测试账号准备控制标记路径无效",
        )
    if target.is_file():
        if target.read_bytes() == b"1":
            return False
        raise JiejianError(
            ErrorCode.IDENTITY_PREPARATION_FAILED,
            "测试账号准备控制标记内容无效",
        )
    temporary = target.with_name(f".{target.name}.tmp-{uuid4().hex}")
    try:
        with temporary.open("xb") as stream:
            stream.write(b"1")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        return True
    except OSError:
        raise JiejianError(
            ErrorCode.IDENTITY_PREPARATION_FAILED,
            "测试账号准备控制标记写入失败",
        ) from None
    finally:
        temporary.unlink(missing_ok=True)


def valid_identity_preparation_marker(path: Path) -> bool:
    try:
        return path.is_file() and path.read_bytes() == b"1"
    except OSError:
        return False
