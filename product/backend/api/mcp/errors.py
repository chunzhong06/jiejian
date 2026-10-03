# 统一 MCP 授权检查和错误净化；验证异常不回显候选原文或秘密。
from __future__ import annotations
from collections.abc import Callable, Mapping
from typing import TypeVar
from mcp import MCPError
from mcp.server.mcpserver import Context
from pydantic import ValidationError
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.agent_access.service import MCPAccessController, MCPAccessLevel

_T = TypeVar("_T")

_ACCESS_ERROR_CODES = {
    ErrorCode.MCP_DISABLED.value: -32041,
    ErrorCode.MCP_AUTH_REQUIRED.value: -32042,
    ErrorCode.MCP_PERMISSION_REQUIRED.value: -32043,
}

def _recovery_for(code: str) -> str:
    return {
        ErrorCode.MCP_DISABLED.value: "请在界鉴的“AI 工具连接”面板中启用连接后重试。",
        ErrorCode.MCP_AUTH_REQUIRED.value: "请从当前界鉴进程复制新的 Bearer 令牌后重试。",
        ErrorCode.MCP_PERMISSION_REQUIRED.value: "请在界鉴中为该应用明确提升临时权限后重试。",
    }.get(code, "请回到界鉴查看当前应用状态并按页面提示恢复。")

def _as_mcp_error(exc: JiejianError) -> MCPError:
    payload = exc.to_dict()
    return MCPError(
        code=_ACCESS_ERROR_CODES.get(exc.code, -32010),
        message=str(payload["message"]),
        data={
            "error_code": exc.code,
            "details": payload.get("details", {}),
            "recovery": _recovery_for(exc.code),
        },
    )

def require_mcp_level(
    access: MCPAccessController,
    ctx: Context,
    required_level: MCPAccessLevel,
    *,
    project_id: str | None = None,
) -> None:
    """每次调用都重新校验 Bearer 与当前 Project 授权。"""

    headers: Mapping[str, str] = ctx.headers or {}
    try:
        access.require(headers.get("authorization"), required_level, project_id=project_id)
    except JiejianError as exc:
        raise _as_mcp_error(exc) from None

def _invoke(operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except JiejianError as exc:
        raise _as_mcp_error(exc) from None
    except ValidationError:
        # 候选中的原文和技术输入不进入SDK异常正文或日志。
        raise _as_mcp_error(JiejianError(ErrorCode.INPUT_INVALID, "工具输入不符合公开合同，请读取上下文中的输入格式")) from None
