# =============================================================================
# 共享秘密存储端口
#
# 定位
#   LLM 与测试身份等业务能力共用的最小秘密持久化抽象。
#
# 职责
#   约束按引用写入、读取、删除和判断是否已配置的四个操作。
#
# 边界
#   端口不解释业务命名空间，也不允许调用方枚举全部秘密。
#
# 调用链
#   Application services → SecretStore → platform adapter
# =============================================================================

from __future__ import annotations

from typing import Protocol

from product.backend.core.errors import ErrorCode, JiejianError


class SecretStore(Protocol):
    """只允许调用方持有精确引用，不提供秘密枚举能力。"""

    def write(self, secret_ref: str, secret: str) -> None: ...

    def read(self, secret_ref: str) -> str | None: ...

    def delete(self, secret_ref: str) -> None: ...

    def configured(self, secret_ref: str | None) -> bool: ...


class UnavailableSecretStore:
    """无平台凭据实现时保留离线控制面，并在实际访问时明确失败。"""

    def write(self, secret_ref: str, secret: str) -> None:
        raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE, "本机秘密存储不可用")

    def read(self, secret_ref: str) -> str | None:
        raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE, "本机秘密存储不可用")

    def delete(self, secret_ref: str) -> None:
        raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE, "本机秘密存储不可用")

    def configured(self, secret_ref: str | None) -> bool:
        if secret_ref is None:
            return False
        raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE, "本机秘密存储不可用")
