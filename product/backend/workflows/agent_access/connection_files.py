# 本机连接器的跨进程回执与 DPAPI 保护文档；不将凭据或配置备份明文写入运行目录。
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConnectionProfile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    schema_version: Literal['1'] = '1'
    client: Literal['dsh', 'codex', 'zcode', 'trae', 'codebuddy', 'qoder']
    endpoint: str
    generation: str = Field(pattern=r'^[a-f0-9]{32}$')

    @field_validator('endpoint')
    @classmethod
    def loopback_only(cls, value):
        parsed = urlsplit(value)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port or parsed.path != '/mcp' or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('仅允许当前本机 MCP 端点')
        return value


class ConnectionReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    schema_version: Literal['1'] = '1'
    generation: str = Field(pattern=r'^[a-f0-9]{32}$')
    state: Literal['STARTED', 'TOOLS_READ', 'REQUEST_ACCEPTED', 'DISCONNECTED', 'FAILED']
    code: Literal['NONE', 'SERVICE_UNAVAILABLE', 'AUTH_REJECTED', 'SESSION_EXPIRED', 'PROTOCOL_ERROR', 'CREDENTIAL_UNAVAILABLE', 'EMPTY_TOOLS'] = 'NONE'
    tool_count: int = Field(default=0, ge=0, le=10000)
    at_us: int = Field(ge=0)


class ConnectionBackup(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, hide_input_in_errors=True)
    schema_version: Literal['1'] = '1'
    target: str = Field(min_length=1, max_length=32768)
    before: str | None = Field(default=None, max_length=4_000_000, pattern=r'^(?:[0-9a-f]{2})*$')
    after_hash: str = Field(pattern=r'^[a-f0-9]{64}$')


def protect(value: bytes) -> bytes:
    import win32crypt
    return win32crypt.CryptProtectData(value, 'Jiejian Agent connection', b'jiejian-agent-connection-v1', None, None, 1)


def unprotect(value: bytes) -> bytes:
    import win32crypt
    return win32crypt.CryptUnprotectData(value, b'jiejian-agent-connection-v1', None, None, 1)[1]


def atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.resolve() != path.absolute() or path.is_symlink():
        raise ValueError('连接文件路径包含链接')
    fd, temporary = tempfile.mkstemp(prefix='.jiejian-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def read_profile(path: Path) -> ConnectionProfile:
    if path.stat().st_size > 16384:
        raise ValueError('连接记录大小超限')
    return ConnectionProfile.model_validate_json(unprotect(path.read_bytes()))
