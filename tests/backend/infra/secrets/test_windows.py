# 验证 Windows SecretStore 适配器只精确读写和删除指定凭据，不依赖系统枚举。

from __future__ import annotations

import ctypes

import product.backend.infra.secrets.windows as secrets_module
from product.backend.infra.secrets import WindowsCredentialManagerSecretStore


class _FakeAdvapi32:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self._allocations: list[object] = []

    def CredWriteW(self, credential_pointer, _flags: int) -> bool:
        credential = credential_pointer._obj
        self.values[credential.TargetName] = ctypes.string_at(
            credential.CredentialBlob,
            credential.CredentialBlobSize,
        )
        return True

    def CredReadW(self, target: str, _kind: int, _flags: int, result_pointer) -> bool:
        value = self.values.get(target)
        if value is None:
            ctypes.set_last_error(1168)
            return False
        blob = ctypes.create_string_buffer(value)
        credential = secrets_module._CREDENTIALW()
        credential.CredentialBlobSize = len(value)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential_pointer = ctypes.pointer(credential)
        result = ctypes.cast(
            result_pointer,
            ctypes.POINTER(ctypes.POINTER(secrets_module._CREDENTIALW)),
        )
        result[0] = credential_pointer
        self._allocations.extend((blob, credential, credential_pointer))
        return True

    def CredDeleteW(self, target: str, _kind: int, _flags: int) -> bool:
        if target not in self.values:
            ctypes.set_last_error(1168)
            return False
        del self.values[target]
        return True

    def CredFree(self, _credential_pointer) -> None:
        return None


def test_windows_secret_store_exactly_reads_writes_and_deletes_pairing(
    monkeypatch,
) -> None:
    fake = _FakeAdvapi32()
    monkeypatch.setattr(secrets_module, "_advapi32", lambda: fake)
    store = object.__new__(WindowsCredentialManagerSecretStore)
    secret_ref = "cred:jiejian/mcp-control/pairing"

    assert store.read(secret_ref) is None
    store.write(secret_ref, "pairing-secret")
    assert store.read(secret_ref) == "pairing-secret"
    store.delete(secret_ref)
    assert store.read(secret_ref) is None
