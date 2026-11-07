"""业务指纹沿用相同 JSON 字节约定；不对载荷做额外模型转换。"""
import hashlib
import json
from typing import Any


def canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
