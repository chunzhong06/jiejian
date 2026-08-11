"""Worker 与 Runner 子进程的显式最小环境构造边界。"""

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
