# =============================================================================
# 共享秘密引用规范
#
# 定位
#   业务命名空间与平台秘密存储目标名称之间的纯校验边界。
#
# 职责
#   构造受限 credential 引用｜拒绝未知命名空间、路径穿越和歧义分段。
#
# 边界
#   只处理引用文本，不访问秘密存储，也不接受任意 cred: 目标名称。
#
# 调用链
#   LLM / TestIdentity → refs → Windows Credential Manager adapter
# =============================================================================

from __future__ import annotations

import re


_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_NAMESPACE_DEPTHS = {
    "llm": 1,
    "test-identity": 3,
}


def credential_ref(namespace: str, *segments: str) -> str:
    """构造并复核一个界鉴自有的 credential 引用。"""

    return validate_credential_secret_ref(
        "/".join(("cred:jiejian", namespace, *segments))
    )


def validate_credential_secret_ref(value: str) -> str:
    """只接受已登记命名空间及其固定深度，防止跨业务读取秘密。"""

    prefix = "cred:jiejian/"
    if not isinstance(value, str) or value != value.strip() or not value.startswith(prefix):
        raise ValueError("secret_ref must use a registered jiejian credential namespace")
    parts = value.removeprefix(prefix).split("/")
    namespace = parts[0] if parts else ""
    expected_depth = _NAMESPACE_DEPTHS.get(namespace)
    segments = parts[1:]
    if expected_depth is None or len(segments) != expected_depth:
        raise ValueError("secret_ref credential namespace or depth is invalid")
    if any(_SEGMENT.fullmatch(segment) is None for segment in segments):
        raise ValueError("secret_ref credential segment is invalid")
    return "/".join((prefix.removesuffix("/"), namespace, *segments))
