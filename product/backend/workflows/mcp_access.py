# =============================================================================
# MCP 本机配对与会话访问控制
#
# 定位
#   SecretStore、GUI 管理面与 MCP Streamable HTTP 入口之间的凭据和权限边界。
#
# 职责
#   持久化长期配对令牌｜维护当前 serve 的 READ/PREPARE/EXECUTE｜投影连接活动。
#
# 边界
#   Token 只进入 SecretStore 和显式凭据响应；提升授权与活动永远只驻留当前进程。
# =============================================================================

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from enum import StrEnum
from hmac import compare_digest
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.secrets import SecretStore, credential_ref


MCP_PAIRING_SECRET_REF = credential_ref("mcp-control", "pairing")


class MCPAccessLevel(StrEnum):
    READ = "READ"
    PREPARE = "PREPARE"
    EXECUTE = "EXECUTE"


_LEVEL_ORDER = {
    MCPAccessLevel.READ: 0,
    MCPAccessLevel.PREPARE: 1,
    MCPAccessLevel.EXECUTE: 2,
}


class _MCPAccessModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class MCPProjectGrant(_MCPAccessModel):
    project_id: str = Field(min_length=1, max_length=64)
    level: MCPAccessLevel


class MCPAccessView(_MCPAccessModel):
    schema_version: Literal["1"] = "1"
    paired: bool
    accepting_connections: bool
    endpoint: str = Field(min_length=1, max_length=2048)
    default_level: Literal[MCPAccessLevel.READ] = MCPAccessLevel.READ
    project_grants: tuple[MCPProjectGrant, ...] = ()
    client_connected: bool = False
    client_name: str | None = Field(default=None, max_length=128)
    client_version: str | None = Field(default=None, max_length=128)
    last_seen_at_us: int | None = Field(default=None, ge=0)


class MCPAccessCredentialView(MCPAccessView):
    access_token: str = Field(min_length=32, max_length=256)


class MCPAccessController:
    """以单锁保证长期配对和当前 serve 授权对并发请求立即生效。"""

    def __init__(
        self,
        endpoint: str,
        secret_store: SecretStore,
        *,
        clock_us: Callable[[], int] | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._secret_store = secret_store
        self._clock_us = clock_us or (lambda: time.time_ns() // 1_000)
        try:
            self._token = secret_store.read(MCP_PAIRING_SECRET_REF)
        except JiejianError as exc:
            if exc.code != ErrorCode.SECRET_STORE_UNAVAILABLE.value:
                raise
            self._token = None
        self._accepting_connections = self._token is not None
        self._grants: dict[str, MCPAccessLevel] = {}
        self._client_name: str | None = None
        self._client_version: str | None = None
        self._last_seen_at_us: int | None = None
        self._lock = RLock()

    def view(self) -> MCPAccessView:
        with self._lock:
            return self._view_locked()

    def pair(self) -> MCPAccessCredentialView:
        with self._lock:
            if self._token is None:
                # token_urlsafe(32) 的原始随机输入为 32 字节，即 256 bit。
                token = secrets.token_urlsafe(32)
                self._secret_store.write(MCP_PAIRING_SECRET_REF, token)
                self._token = token
                self._grants.clear()
            self._accepting_connections = True
            return self._credential_view_locked()

    def rotate(self) -> MCPAccessCredentialView:
        with self._lock:
            if self._token is None:
                raise JiejianError(
                    ErrorCode.MCP_DISABLED,
                    "尚未建立 MCP 配对，请先在 AI 工具连接面板中完成首次配对。",
                )
            token = secrets.token_urlsafe(32)
            self._secret_store.write(MCP_PAIRING_SECRET_REF, token)
            self._token = token
            self._accepting_connections = True
            self._clear_session_locked()
            return self._credential_view_locked()

    def reveal(self) -> MCPAccessCredentialView:
        with self._lock:
            if self._token is None:
                raise JiejianError(
                    ErrorCode.MCP_DISABLED,
                    "尚未建立 MCP 配对，请先在 AI 工具连接面板中完成首次配对。",
                )
            return self._credential_view_locked()

    def pause(self) -> MCPAccessView:
        with self._lock:
            self._accepting_connections = False
            self._clear_session_locked()
            return self._view_locked()

    def forget(self) -> MCPAccessView:
        with self._lock:
            self._secret_store.delete(MCP_PAIRING_SECRET_REF)
            self._token = None
            self._accepting_connections = False
            self._clear_session_locked()
            return self._view_locked()

    def set_level(self, project_id: str, level: MCPAccessLevel) -> MCPAccessView:
        with self._lock:
            if self._token is None or not self._accepting_connections:
                raise JiejianError(
                    ErrorCode.MCP_DISABLED,
                    "当前 serve 未接受 MCP 连接，请回到 AI 工具连接面板查看状态。",
                )
            if level is MCPAccessLevel.READ:
                self._grants.pop(project_id, None)
            else:
                self._grants[project_id] = level
            return self._view_locked()

    def level_for(self, project_id: str) -> MCPAccessLevel:
        with self._lock:
            return self._grants.get(project_id, MCPAccessLevel.READ)

    def authorize(self, authorization: str | None) -> None:
        with self._lock:
            self._authorize_locked(authorization)

    def require(
        self,
        authorization: str | None,
        required_level: MCPAccessLevel,
        *,
        project_id: str | None = None,
    ) -> None:
        with self._lock:
            self._authorize_locked(authorization)
            if required_level is MCPAccessLevel.READ:
                return
            if project_id is None:
                raise ValueError("project_id is required above READ")
            current = self._grants.get(project_id, MCPAccessLevel.READ)
            if _LEVEL_ORDER[current] < _LEVEL_ORDER[required_level]:
                raise JiejianError(
                    ErrorCode.MCP_PERMISSION_REQUIRED,
                    "当前应用的 MCP 权限不足，请在界鉴中明确提升后重试。",
                    details={
                        "required_level": required_level.value,
                        "project_id": project_id,
                    },
                )

    def close(self) -> None:
        with self._lock:
            # 进程退出只清理本次 serve；长期配对仍由 SecretStore 保存。
            self._token = None
            self._accepting_connections = False
            self._clear_session_locked()

    def note_activity(
        self,
        client_name: str | None,
        client_version: str | None,
    ) -> None:
        """记录 SDK 已验证连接的有界身份和最近活动，不保存请求正文。"""

        with self._lock:
            if self._token is None or not self._accepting_connections:
                return
            self._client_name = self._bounded_client_value(client_name)
            self._client_version = self._bounded_client_value(client_version)
            self._last_seen_at_us = self._clock_us()

    def _authorize_locked(self, authorization: str | None) -> None:
        if self._token is None or not self._accepting_connections:
            raise JiejianError(
                ErrorCode.MCP_DISABLED,
                "当前 serve 未接受 MCP 连接，请回到界鉴查看连接状态。",
            )
        scheme, separator, presented = (authorization or "").partition(" ")
        if (
            separator != " "
            or scheme.casefold() != "bearer"
            or not presented
            or not compare_digest(presented, self._token)
        ):
            raise JiejianError(
                ErrorCode.MCP_AUTH_REQUIRED,
                "MCP Bearer 令牌缺失或已经失效，请复制当前令牌后重试。",
            )

    def _view_locked(self) -> MCPAccessView:
        return MCPAccessView(
            paired=self._token is not None,
            accepting_connections=self._accepting_connections,
            endpoint=self._endpoint,
            project_grants=tuple(
                MCPProjectGrant(project_id=project_id, level=level)
                for project_id, level in sorted(self._grants.items())
            ),
            client_connected=self._last_seen_at_us is not None,
            client_name=self._client_name,
            client_version=self._client_version,
            last_seen_at_us=self._last_seen_at_us,
        )

    def _credential_view_locked(self) -> MCPAccessCredentialView:
        assert self._token is not None
        return MCPAccessCredentialView(
            **self._view_locked().model_dump(),
            access_token=self._token,
        )

    def _clear_session_locked(self) -> None:
        self._grants.clear()
        self._client_name = None
        self._client_version = None
        self._last_seen_at_us = None

    @staticmethod
    def _bounded_client_value(value: str | None) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()[:128]
        return normalized or None


__all__ = [
    "MCPAccessController",
    "MCPAccessCredentialView",
    "MCPAccessLevel",
    "MCPAccessView",
    "MCP_PAIRING_SECRET_REF",
    "MCPProjectGrant",
]
