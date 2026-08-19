# =============================================================================
# LLM 秘密存储
#
# 定位
# LLM profile 与 Windows Credential Manager 之间的秘密引用边界。
#
# 职责
# 定义秘密存储端口｜持久化泛型凭据｜解析受限 credential 引用
#
# 边界
# 数据库只保存 cred:jiejian/llm 引用；秘密正文不得进入模型、日志或异常。
#
# 调用链
# LLMProfileRegistry → LLMSecretStore → Windows Credential Manager
# =============================================================================

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Protocol

from product.backend.infra.llm.config import LLMProfileConfig, validate_credential_secret_ref


class LLMSecretStore(Protocol):
    def write(self, secret_ref: str, secret: str) -> None: ...

    def read(self, secret_ref: str) -> str | None: ...

    def delete(self, secret_ref: str) -> None: ...

    def configured(self, secret_ref: str | None) -> bool: ...


class WindowsCredentialManagerSecretStore:
    """使用泛型凭据保存秘密；数据库只保存 cred:jiejian/llm/<profile> 引用。"""

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
        if not _advapi32().CredReadW(_target_name(secret_ref), self._CRED_TYPE_GENERIC, 0, ctypes.byref(credential_ptr)):
            error = ctypes.get_last_error()
            if error == 1168:  # ERROR_NOT_FOUND
                return None
            raise OSError(error, "CredReadW failed")
        try:
            blob = ctypes.string_at(credential_ptr.contents.CredentialBlob, credential_ptr.contents.CredentialBlobSize)
            return blob.decode("utf-8")
        finally:
            _advapi32().CredFree(credential_ptr)

    def delete(self, secret_ref: str) -> None:
        if not _advapi32().CredDeleteW(_target_name(secret_ref), self._CRED_TYPE_GENERIC, 0):
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
    library.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
    library.CredReadW.restype = wintypes.BOOL
    library.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    library.CredDeleteW.restype = wintypes.BOOL
    library.CredFree.argtypes = [ctypes.c_void_p]
    library.CredFree.restype = None
    return library


def _target_name(secret_ref: str) -> str:
    return validate_credential_secret_ref(secret_ref).removeprefix("cred:")


def credential_ref_for(profile: LLMProfileConfig) -> str:
    return f"cred:jiejian/llm/{profile.profile_name}"
