# 统一根文档的严格 JSON 读取与确定性编码；格式身份必须由字节显式携带。
from __future__ import annotations

import json
import math


def encode_json(payload: dict) -> bytes:
    # 排序、紧凑分隔和有限数字共同定义摘要输入；不能用另一套等价 JSON 文本代替这些字节。
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")


def decode_json(raw: bytes | str, *, limit: int | None = None) -> dict:
    """读取 UTF-8 JSON 对象，拒绝歧义字节及非有限数字，不回显输入。"""
    if not isinstance(raw, (bytes, str)):
        raise TypeError("JSON reader requires bytes or text")

    def unique(pairs):
        # JSON 默认会覆盖重复键；跨 reader 的取值差异会破坏关联和摘要核验，因此显式拒绝。
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_):
        raise ValueError("nonfinite JSON number")

    def finite_number(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("nonfinite JSON number")
        return number

    try:
        wire = raw.encode("utf-8") if isinstance(raw, str) else raw
        if (limit is not None and len(wire) > limit) or wire.startswith(b"\xef\xbb\xbf"):
            raise ValueError("invalid document bytes")
        payload = json.loads(wire.decode("utf-8"), object_pairs_hook=unique,
                             parse_constant=nonfinite, parse_float=finite_number)
    except (UnicodeError, RecursionError, ValueError):
        raise ValueError("invalid JSON document") from None
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def decode_document(raw: bytes, *, document_type: str, version: str, limit: int) -> dict:
    # 除字段身份外还要求原字节就是 canonical 编码；语义相同的宽松 JSON 不属于这个交换格式。
    if type(raw) is not bytes:
        raise ValueError("invalid document bytes")
    payload = decode_json(raw, limit=limit)
    if (payload.get("document_type") != document_type
            or payload.get("schema_version") != version or encode_json(payload) != raw):
        raise ValueError("unsupported or noncanonical document")
    return payload
