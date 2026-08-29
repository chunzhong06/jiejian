# =============================================================================
# MCP 进程内访问控制
#
# 定位
#   GUI 管理面与 MCP Streamable HTTP 入口之间的短期令牌和逐 Project 权限边界。
#
# 职责
#   生成随机 Bearer 令牌｜维护 READ/PREPARE/EXECUTE 层级｜即时撤销令牌和授权。
#
# 边界
#   令牌与授权只驻留当前进程内存，不持久化、不写日志，也不复用浏览器控制 Cookie。
# =============================================================================

from __future__ import annotations

import secrets
from enum import StrEnum
from hmac import compare_digest
from threading import RLock
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError


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
    enabled: bool
    endpoint: str = Field(min_length=1, max_length=2048)
    access_token: str | None = Field(default=None, min_length=32, max_length=256)
    default_level: Literal[MCPAccessLevel.READ] = MCPAccessLevel.READ
    project_grants: tuple[MCPProjectGrant, ...] = ()


class MCPAccessController:
    """以单锁保证令牌轮换、关闭和权限检查对并发请求立即生效。"""

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._token: str | None = None
        self._grants: dict[str, MCPAccessLevel] = {}
        self._lock = RLock()

    def view(self) -> MCPAccessView:
        with self._lock:
            return self._view_locked()

    def enable(self) -> MCPAccessView:
        with self._lock:
            if self._token is None:
                # token_urlsafe(32) 的原始随机输入为 32 字节，即 256 bit。
                self._token = secrets.token_urlsafe(32)
                self._grants.clear()
            return self._view_locked()

    def regenerate(self) -> MCPAccessView:
        with self._lock:
            if self._token is None:
                raise JiejianError(
                    ErrorCode.MCP_DISABLED,
                    "MCP 控制入口尚未启用，请先在 AI 工具连接面板中启用。",
                )
            self._token = secrets.token_urlsafe(32)
            self._grants.clear()
            return self._view_locked()

    def disable(self) -> MCPAccessView:
        with self._lock:
            self._token = None
            self._grants.clear()
            return self._view_locked()

    def set_level(self, project_id: str, level: MCPAccessLevel) -> MCPAccessView:
        with self._lock:
            if self._token is None:
                raise JiejianError(
                    ErrorCode.MCP_DISABLED,
                    "MCP 控制入口尚未启用，请先在 AI 工具连接面板中启用。",
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
        self.disable()

    def _authorize_locked(self, authorization: str | None) -> None:
        if self._token is None:
            raise JiejianError(
                ErrorCode.MCP_DISABLED,
                "MCP 控制入口尚未启用，请在界鉴中启用后重试。",
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
            enabled=self._token is not None,
            endpoint=self._endpoint,
            access_token=self._token,
            project_grants=tuple(
                MCPProjectGrant(project_id=project_id, level=level)
                for project_id, level in sorted(self._grants.items())
            ),
        )


__all__ = [
    "MCPAccessController",
    "MCPAccessLevel",
    "MCPAccessView",
    "MCPProjectGrant",
]
