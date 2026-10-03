# 将 loopback MCP 挂载与 Bearer 门禁适配到 ASGI；不承接业务事务。
from __future__ import annotations
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.agent_access.service import MCPAccessController
from product.backend.api.mcp.errors import _recovery_for

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
