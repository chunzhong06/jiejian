# =============================================================================
# Execution 最小子进程环境
#
# 定位
#   Worker 启动 Runner 前筛选环境变量和运行时路径的边界
#
# 职责
#   保留 Python/系统必要变量｜按需注入授权 secret｜拒绝无关父进程环境传播
#
# 边界
#   只传播 allowlist 与显式授权名称；调用方不得以完整 os.environ 绕过筛选。
#
# 调用链
#   RunnerSupervisor / RecordingJobHandler → minimal_process_environment → subprocess
# =============================================================================

from __future__ import annotations

from collections.abc import Mapping, Sequence

_BASE_KEYS = (
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "LOCALAPPDATA",
    "PLAYWRIGHT_BROWSERS_PATH",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "WINDIR",
)


def minimal_process_environment(
    source: Mapping[str, str],
    *,
    secret_names: Sequence[str] = (),
) -> dict[str, str]:
    """只传递 Python 运行所需键和本次快照引用的秘密。"""

    selected_names = tuple(dict.fromkeys((*_BASE_KEYS, *secret_names)))
    by_casefold = {key.casefold(): (key, value) for key, value in source.items()}
    result: dict[str, str] = {}
    for name in selected_names:
        selected = by_casefold.get(name.casefold())
        if selected is not None and selected[1]:
            result[name] = selected[1]
    result["PYTHONDONTWRITEBYTECODE"] = "1"
    result["PYTHONUTF8"] = "1"
    return result
