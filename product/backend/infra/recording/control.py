# =============================================================================
# Recording attempt 控制标记
#
# 定位
#   API/ApplicationCore 与 Recording Runner 之间的当前尝试控制事实边界
#
# 职责
#   固定标记命名｜原子写入无秘密值｜校验标记类型和内容
#
# 边界
#   不保存用户输入、凭据或录制事件；调用者必须先绑定到当前 attempt 目录。
#
# 调用链
#   RecordingLifecycle / RecordingJobHandler → control markers → recording_process
# =============================================================================

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError


@dataclass(frozen=True, slots=True)
class RecordingControlPaths:
    """一个已解析 attempt 目录内的录制控制标记路径。"""

    attempt_dir: Path
    ready_path: Path
    start_path: Path
    started_path: Path
    stop_path: Path


def control_paths_for_attempt(attempt_dir: Path) -> RecordingControlPaths:
    """返回当前 attempt 的固定控制文件名，并拒绝目录越界。"""

    root = attempt_dir.resolve()
    if not root.is_dir():
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制当前 attempt 尚未就绪")
    return RecordingControlPaths(
        attempt_dir=root,
        ready_path=root / "capture.ready",
        start_path=root / "capture.start",
        started_path=root / "capture.started",
        stop_path=root / "capture.stop",
    )


def write_control_marker(path: Path, *, attempt_dir: Path) -> bool:
    """原子写入固定值标记；已存在的同值标记返回 ``False``。"""

    root = attempt_dir.resolve()
    target = path.resolve()
    if target.parent != root or target.name not in {
        "capture.ready",
        "capture.start",
        "capture.started",
        "capture.stop",
    }:
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制控制标记路径无效")
    if target.is_file():
        if target.read_bytes() == b"1":
            return False
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制控制标记内容无效")
    if target.exists():
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制控制标记类型无效")
    temporary = target.with_name(f".{target.name}.tmp-{uuid4().hex}")
    try:
        with temporary.open("xb") as stream:
            stream.write(b"1")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        return True
    except OSError:
        raise JiejianError(ErrorCode.RECORD_STATE_PRECONDITION, "录制控制标记写入失败") from None
    finally:
        temporary.unlink(missing_ok=True)


def valid_control_marker(path: Path) -> bool:
    """只把当前版本的固定无秘密标记视为有效控制事实。"""

    try:
        return path.is_file() and path.read_bytes() == b"1"
    except OSError:
        return False
