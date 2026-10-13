# 创建响应只提供有限对象定位；不把响应状态或编号当成权限结果证明。
from __future__ import annotations

import json
import re
from urllib.parse import unquote, urljoin, urlsplit

from product.backend.core.redaction import REDACTED

CREATED_RESOURCE_EXTRACTOR = "created_resource_id"
_PRIVATE = re.compile(r"token|secret|password|passwd|cookie|authorization|credential|api.?key|id.?card|ssn|email|phone|address|full.?name", re.I)


def resource_identifier(value):
    """仅接受单个非秘密标识，路径、布尔值、容器和脱敏占位均拒绝。"""
    if type(value) not in {str, int}:
        return None
    text = str(value)
    if re.fullmatch(r"[\w.-]{1,256}", text) is None or text in {".", ".."} or REDACTED in text:
        return None
    return text


def location_resource(location, request_url):
    """Location 必须指向同源、无查询的具体子资源，不能把外站或集合名当编号。"""
    if not isinstance(location, str) or not location or "\\" in location:
        return None
    base, resolved = urlsplit(request_url), urlsplit(urljoin(request_url, location))
    if ((base.scheme, base.hostname, base.port) != (resolved.scheme, resolved.hostname, resolved.port)
            or resolved.username or resolved.password or resolved.query or resolved.fragment):
        return None
    parts = [unquote(part) for part in resolved.path.split("/") if part]
    original = [unquote(part) for part in base.path.split("/") if part]
    if not parts or parts == original or any(part in {".", ".."} for part in parts):
        return None
    return resource_identifier(parts[-1])


def response_object_candidates(body, headers, request_url):
    """从有界响应中枚举编号字段；来源歧义保留给人，绝不选择第一个值。"""
    candidates = []
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("ambiguous response field")
            result[key] = value
        return result
    try:
        payload = json.loads(body, object_pairs_hook=unique_object) if body else None
    except (ValueError, TypeError):
        payload = None

    def walk(value, path, depth=0):
        if depth > 8 or len(candidates) >= 64 or not isinstance(value, dict):
            return
        for key, child in value.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", key) or _PRIVATE.search(key):
                continue
            location = f"{path}.{key}"
            if len(re.findall(r"\.[A-Za-z_][A-Za-z0-9_-]*|\[[0-9]+\]", location)) > 8:
                continue
            identifier = resource_identifier(child)
            if re.search(r"(^id$|_id$|Id$|ID$)", key) and identifier is not None:
                candidates.append(("RESPONSE_JSON", location, identifier))
            if isinstance(child, dict):
                walk(child, location, depth + 1)
            elif isinstance(child, list):
                for index, item in enumerate(child[:64]):
                    walk(item, f"{location}[{index}]", depth + 1)
    walk(payload, "$")
    locations = [value for name, value in headers if name.lower() == "location"]
    if len(locations) == 1:
        identifier = location_resource(locations[0], request_url)
        if identifier is not None:
            candidates.append(("RESPONSE_LOCATION", "$location", identifier))
    return tuple(candidates[:64])
