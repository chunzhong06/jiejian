# API 错误映射
# 将内部稳定错误转换为脱敏 HTTP envelope；原始异常细节不得越过此边界。

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.failures import ErrorKind, failure_kind


def _status_for(code: str) -> int:
    return {ErrorKind.NOT_FOUND: 404, ErrorKind.CONFLICT: 409,
        ErrorKind.UNAVAILABLE: 503, ErrorKind.TOO_LARGE: 413,
        ErrorKind.UNAUTHENTICATED: 401, ErrorKind.FORBIDDEN: 403,
        ErrorKind.INTERNAL: 500, ErrorKind.EXHAUSTED: 429, ErrorKind.INVALID: 400}[failure_kind(code)]


async def jiejian_error_handler(request: Request, exc: JiejianError) -> JSONResponse:
    error = exc.to_dict()
    return JSONResponse(
        status_code=_status_for(exc.code),
        content={
            "schema_version": "1",
            "error": error,
            "trace_id": request.state.trace_id,
        },
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError | ValidationError
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        # 内部持久记录/投影校验失败不能归咎于用户参数；日志只含受控身份，不含异常值。
        import logging
        import re
        from product.backend import __version__
        from product.backend.infrastructure.runtime.frontend_assets import frontend_asset_identity
        identity = frontend_asset_identity(getattr(request.app.state, 'frontend_dir', None))
        refs = {key:value for key,value in request.path_params.items() if key in {'project_id','candidate_id','suggestion_id'}
            and isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_]{1,96}',value)}
        revision = request.query_params.get('revision')
        if revision is not None and revision.isascii() and revision.isdigit() and len(revision) <= 10:
            refs['revision'] = revision
        details = {'version':__version__, 'frontend_identity':identity, 'validation_error_count':exc.error_count(), **refs}
        logging.getLogger("jiejian.interfaces.http.errors").error('Internal record validation trace=%s details=%s', request.state.trace_id, details)
        error = JiejianError(ErrorCode.STORAGE_STATE, '界鉴内部记录校验失败，请保留现有要求与材料，并提供本次记录编号', details=details)
        return JSONResponse(status_code=500, content={'schema_version':'1','error':error.to_dict(),'trace_id':request.state.trace_id})
    fields = {'name', 'operation_id', 'expected_plan_fingerprint', 'expected_version', 'expected_revision', 'plan_hash'}
    reasons = {'missing':'REQUIRED', 'string_too_long':'TOO_LONG', 'string_too_short':'TOO_SHORT'}
    # 只提取公开模型的字段名和稳定原因；input、ctx及任意用户键不进入错误响应。
    field_errors = [{'field':item['loc'][1], 'reason':reasons.get(item['type'], 'INVALID')}
        for item in exc.errors()[:16] if len(item['loc']) == 2 and item['loc'][0] == 'body' and item['loc'][1] in fields]
    error = JiejianError(ErrorCode.INPUT_INVALID, "请求参数无效",
        details={'request_outcome':'NOT_ACCEPTED', 'field_errors':field_errors})
    return JSONResponse(
        status_code=422,
        content={
            "schema_version": "1",
            "error": error.to_dict(),
            "trace_id": request.state.trace_id,
        },
    )
