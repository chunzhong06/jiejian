# 共享秘密存储端口、引用校验与 Windows Credential Manager 实现。

import os

from product.backend.infra.secrets.store import SecretStore, UnavailableSecretStore
from product.backend.infra.secrets.refs import (
    credential_ref,
    validate_credential_secret_ref,
)
from product.backend.infra.secrets.windows import WindowsCredentialManagerSecretStore

__all__ = [
    "SecretStore",
    "UnavailableSecretStore",
    "WindowsCredentialManagerSecretStore",
    "credential_ref",
    "validate_credential_secret_ref",
]


def default_secret_store() -> SecretStore:
    """返回当前平台唯一共享秘密存储；非 Windows 仅提供显式不可用边界。"""

    if os.name == "nt":
        return WindowsCredentialManagerSecretStore()
    return UnavailableSecretStore()
