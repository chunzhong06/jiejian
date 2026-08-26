# =============================================================================
# Windows Credential Manager 秘密存储
#
# 定位
#   共享 SecretStore 端口的 Windows 平台实现。
#
# 职责
#   按严格引用读写泛型凭据｜精确删除单条凭据｜隐藏平台 ctypes 细节。
#
# 边界
#   不枚举凭据；正文只在调用栈和 Credential Manager 中短暂出现。
#
# 调用链
#   SecretStore consumers → WindowsCredentialManagerSecretStore → Advapi32
# =============================================================================

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from product.backend.infra.secrets.refs import validate_credential_secret_ref


_MAX_CREDENTIAL_BLOB_BYTES = 2_560


class WindowsCredentialManagerSecretStore:
    """使用泛型凭据保存界鉴受控命名空间下的秘密。"""

    _CRED_TYPE_GENERIC = 1
    _CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self) -> None:
        if os.name != "nt":
            raise RuntimeError("Windows Credential Manager is only available on Windows")

    def write(self, secret_ref: str, secret: str) -> None:
        if not secret or "\x00" in secret:
            raise ValueError("secret must be non-empty and contain no NUL")
        target = _target_name(secret_ref)
        blob = secret.encode("utf-8")
        if len(blob) > _MAX_CREDENTIAL_BLOB_BYTES:
            raise ValueError("secret exceeds Windows credential byte budget")
        credential = _CREDENTIALW()
        blob_buffer = ctypes.create_string_buffer(blob)
        credential.Type = self._CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(blob_buffer, wintypes.LPBYTE)
        credential.Persist = self._CRED_PERSIST_LOCAL_MACHINE
        if not _advapi32().CredWriteW(ctypes.byref(credential), 0):
            raise OSError(ctypes.get_last_error(), "CredWriteW failed")

    def read(self, secret_ref: str) -> str | None:
        credential_ptr = ctypes.POINTER(_CREDENTIALW)()
        if not _advapi32().CredReadW(
            _target_name(secret_ref),
            self._CRED_TYPE_GENERIC,
            0,
            ctypes.byref(credential_ptr),
        ):
            error = ctypes.get_last_error()
            if error == 1168:  # ERROR_NOT_FOUND
                return None
            raise OSError(error, "CredReadW failed")
        try:
            blob = ctypes.string_at(
                credential_ptr.contents.CredentialBlob,
                credential_ptr.contents.CredentialBlobSize,
            )
            return blob.decode("utf-8")
        finally:
            _advapi32().CredFree(credential_ptr)

    def delete(self, secret_ref: str) -> None:
        if not _advapi32().CredDeleteW(
            _target_name(secret_ref), self._CRED_TYPE_GENERIC, 0
        ):
            error = ctypes.get_last_error()
            if error != 1168:
                raise OSError(error, "CredDeleteW failed")

    def configured(self, secret_ref: str | None) -> bool:
        return secret_ref is not None and self.read(secret_ref) is not None


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", wintypes.LPBYTE),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _advapi32():
    library = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    library.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    library.CredWriteW.restype = wintypes.BOOL
    library.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    library.CredReadW.restype = wintypes.BOOL
    library.CredDeleteW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    library.CredDeleteW.restype = wintypes.BOOL
    library.CredFree.argtypes = [ctypes.c_void_p]
    library.CredFree.restype = None
    return library


def _target_name(secret_ref: str) -> str:
    return validate_credential_secret_ref(secret_ref).removeprefix("cred:")
