# 统一根文档的严格 JSON 读取与确定性编码；格式身份必须由字节显式携带。
from __future__ import annotations

import json


def encode_json(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")


def decode_document(raw: bytes, *, document_type: str, version: str, limit: int) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("nonfinite JSON number")

    if type(raw) is not bytes or len(raw) > limit or raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("invalid document bytes")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)
    except (UnicodeError, RecursionError):
        raise ValueError("invalid JSON document") from None
    if (not isinstance(payload, dict) or payload.get("document_type") != document_type
            or payload.get("schema_version") != version or encode_json(payload) != raw):
        raise ValueError("unsupported or noncanonical document")
    return payload
