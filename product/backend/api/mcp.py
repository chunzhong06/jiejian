# =============================================================================
# MCP Streamable HTTP 只读控制入口
#
# 职责
#   复用同一 ApplicationCore 暴露项目、应用理解、Business Boundary、身份与系统只读事实。
#
# 边界
#   不注册旧 Permission/Check/Recording/Run writer，也不能构造 LOCAL_GUI approval。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from mcp import MCPError
from mcp.server import MCPServer
from mcp.server.context import HandlerResult, ServerRequestContext
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from product.backend import __version__
from product.backend.composition import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.diagnostics import runtime_environment_details
from product.backend.workflows.mcp_access import MCPAccessController, MCPAccessLevel


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


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, tuple | list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    return value


def _understanding_view(value: BaseModel) -> dict[str, Any]:
    payload = value.model_dump(mode="json")
    for field in ("source_root", "source_fingerprint", "endpoint_source_fingerprint"):
        payload.pop(field, None)
    for field in ("role_candidates", "action_candidates"):
        for candidate in payload.get(field, []):
            candidate.pop("evidence", None)
    return payload


class MCPBearerGuard:
    """在 SDK 解析正文前只接受当前进程签发的 Bearer。"""

    def __init__(self, app: ASGIApp, access: MCPAccessController) -> None:
        self._app = app
        self._access = access

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        try:
            self._access.authorize(Headers(scope=scope).get("authorization"))
        except JiejianError as exc:
            payload = exc.to_dict()
            payload["recovery"] = _recovery_for(exc.code)
            response = JSONResponse(
                status_code=401 if exc.code == ErrorCode.MCP_AUTH_REQUIRED.value else 403,
                content={"schema_version": "1", "error": payload},
                headers={"WWW-Authenticate": "Bearer"} if exc.code == ErrorCode.MCP_AUTH_REQUIRED.value else None,
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)


class MCPPathAdapter:
    """把 FastAPI 的精确 /mcp 挂载适配为 SDK 子应用根路径。"""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        adapted = dict(scope)
        adapted["root_path"] = f"{scope.get('root_path', '')}/mcp"
        adapted["path"] = "/"
        adapted["raw_path"] = b"/"
        await self._app(adapted, receive, send)


@dataclass(frozen=True, slots=True)
class MCPControl:
    server: MCPServer
    app: ASGIApp


def build_mcp_control(
    context: ApplicationCore,
    access: MCPAccessController,
    *,
    control_origin: str,
    control_host: str,
) -> MCPControl:
    """注册只读白名单，并绑定当前 loopback origin。"""

    async def record_client_activity(
        request: ServerRequestContext[Any, Any],
        call_next: Callable[[ServerRequestContext[Any, Any]], Any],
    ) -> HandlerResult:
        result = await call_next(request)
        params = request.session.client_params
        access.note_activity(
            None if params is None else params.client_info.name,
            None if params is None else params.client_info.version,
        )
        return result

    server = MCPServer(
        "界鉴 JIEJIAN",
        description="界鉴本地只读控制入口；Business Boundary 只能由本机 GUI 批准。",
        instructions=(
            "READ 只能读取已经形成的项目、应用理解、业务边界、权限 revision 和测试身份事实。"
            "本版本 MCP 不提供业务边界批准、权限写入、检查、录制或运行工具；需要人类决定时请用户回到界鉴。"
        ),
        version=__version__,
        middleware=[record_client_activity],
    )

    @server.tool(name="jiejian_project_list", structured_output=True)
    def project_list(ctx: Context, include_archived: bool = False) -> list[dict[str, Any]]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ)
        return _json(_invoke(lambda: context.projects.list(include_archived=include_archived)))

    @server.tool(name="jiejian_project_show", structured_output=True)
    def project_show(ctx: Context, project_id: str) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.projects.get(project_id)))

    @server.tool(name="jiejian_application_understanding", structured_output=True)
    def application_understanding(ctx: Context, project_id: str) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _understanding_view(_invoke(lambda: context.application_understanding.get(project_id)))

    @server.tool(name="jiejian_business_boundary", structured_output=True)
    def business_boundary(ctx: Context, project_id: str) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.business_boundaries.view(project_id)))

    @server.tool(name="jiejian_intent_show", structured_output=True)
    def intent_show(ctx: Context, project_id: str, intent_id: str) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.permission_intents.history(project_id, intent_id)))

    @server.tool(name="jiejian_identity_list", structured_output=True)
    def identity_list(ctx: Context, project_id: str) -> list[dict[str, Any]]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.test_identities.list(project_id)))

    @server.tool(name="jiejian_system_status", structured_output=True)
    def system_status(ctx: Context) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ)
        environment = runtime_environment_details()
        return {
            "schema_version": "1",
            "version": __version__,
            "api": "available",
            "worker": "unavailable",
            "browser": environment["playwright"]["status"],
            "recovered_jobs": 0,
        }

    sdk_app = server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[control_host],
            allowed_origins=[control_origin],
        ),
        host="127.0.0.1",
    )
    return MCPControl(server=server, app=MCPPathAdapter(MCPBearerGuard(sdk_app, access)))


__all__ = [
    "MCPBearerGuard", "MCPControl", "MCPPathAdapter", "build_mcp_control", "require_mcp_level",
]
