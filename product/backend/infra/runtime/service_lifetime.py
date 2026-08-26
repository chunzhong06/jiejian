# Serve 生存期探针：Worker 只相信锁句柄与随机 owner token，不根据 PID 猜测。

from __future__ import annotations

import json
from pathlib import Path

from product.backend.infra.runtime.process.lock import lock_is_available


def serve_owner_is_alive(path: Path, owner_token: str) -> bool:
    """确认同一 token 的控制面仍持有系统文件锁；半写文件按失联处理。"""

    try:
        with path.open("rb") as stream:
            stream.seek(1)
            payload = json.loads(stream.read().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if payload.get("schema_version") != "1" or payload.get("owner_token") != owner_token:
        return False
    try:
        return not lock_is_available(path)
    except OSError:
        return False
