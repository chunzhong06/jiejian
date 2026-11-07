"""框架解析前的实体预算与文件有界读取；领域内容和归属仍由路由接受。"""
from fastapi import Request
import re
from starlette.requests import ClientDisconnect
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from product.backend.domain.errors import ErrorCode, JiejianError

API_JSON_LIMIT = 8 * 1024 * 1024
# 来源 raw 最多4MiB，外层JSON可把一个字节转义成六个字符；领域预算仍核对解码后的原文。
SOURCE_JSON_LIMIT = 6 * 4_194_304 + 65_536
MCP_JSON_LIMIT = 4 * 1024 * 1024


class BodyBudgetExceeded(HTTPException):
    """保留解析前的 413；FastAPI 不应把接收预算错误改成 JSON 解析失败。"""
    def __init__(self):
        super().__init__(413)


async def body_budget_error(request: Request, exc: BodyBudgetExceeded) -> JSONResponse:
    error = JiejianError(ErrorCode.REQUEST_TOO_LARGE, '请求正文超过接收预算，请缩小本次资料')
    return JSONResponse(status_code=413, content={'schema_version':'1','error':error.to_dict(),
        'trace_id':request.scope.get('state',{}).get('trace_id')})


async def read_bounded_body(request: Request, *, limit: int, message: str,
                            code: ErrorCode = ErrorCode.INPUT_INVALID) -> bytes:
    """逐块执行实际字节上限，超限立即停止读取，不依赖 Content-Length 声明。"""
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > limit:
            raise JiejianError(code, message)
        content.extend(chunk)
    return bytes(content)


class ApiBodyBudget:
    """本机门禁之后、框架解析之前限制实体；不接管MCP长连接或文件领域预算。"""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        path = scope.get('path', '')
        if scope['type'] != 'http' or not path.startswith('/api/') or scope['method'] not in ('POST','PUT','PATCH','DELETE'):
            return await self.app(scope, receive, send)
        # 只有准确的参照文件入口使用流式文件预算；伪造媒体类型不能绕过普通API实体限制。
        if scope['method'] == 'POST' and re.fullmatch(r'/api/projects/[^/]+/proof-preparation/reference-inputs', path):
            return await self.app(scope, receive, send)
        limit = SOURCE_JSON_LIMIT if path.endswith('/api-sources/preview') else API_JSON_LIMIT
        received = 0
        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message['type']=='http.request':
                received += len(message.get('body',b''))
                if received > limit:raise BodyBudgetExceeded()
            return message
        try:
            # 不预读或重放：小接口的领域预算仍能在较早的块停止读取。
            await self.app(scope, bounded_receive, send)
        except ClientDisconnect:
            return
        except BodyBudgetExceeded as exc:
            response = await body_budget_error(Request(scope),exc)
            await response(scope, receive, send)
