# API 错误映射
# 将内部稳定错误转换为脱敏 HTTP envelope；原始异常细节不得越过此边界。

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from product.backend.core.errors import ErrorCode, JiejianError


def _status_for(code: str) -> int:
    if code in {
        ErrorCode.PROJECT_NOT_FOUND.value,
        ErrorCode.APPLICATION_UNDERSTANDING_NOT_FOUND.value,
        ErrorCode.APPLICATION_CANDIDATE_NOT_FOUND.value,
        ErrorCode.CONTRACT_NOT_FOUND.value,
        ErrorCode.RECORD_NOT_FOUND.value,
        ErrorCode.JOB_NOT_FOUND.value,
        ErrorCode.REPORT_NOT_FOUND.value,
        ErrorCode.ARTIFACT_NOT_PUBLISHED.value,
        ErrorCode.EXECUTION_PROFILE_NOT_FOUND.value,
        ErrorCode.RESULT_FINALIZATION_NOT_FOUND.value,
        ErrorCode.BOUNDARY_PROPOSAL_NOT_FOUND.value,
    }:
        return 404
    if code in {
        ErrorCode.STATE_PRECONDITION.value,
        ErrorCode.JOB_IDEMPOTENCY_CONFLICT.value,
        ErrorCode.PROJECT_SOURCE_DRIFT.value,
        ErrorCode.PROJECT_NOT_REVALIDATED.value,
        ErrorCode.PROJECT_ARCHIVE_CONFLICT.value,
        ErrorCode.APPLICATION_REVISION_CONFLICT.value,
        ErrorCode.APPLICATION_CANDIDATE_CONFLICT.value,
        ErrorCode.CONTRACT_NOT_ACTIVE.value,
        ErrorCode.JOB_CANCEL_CONFLICT.value,
        ErrorCode.JOB_TERMINAL_CONFLICT.value,
        ErrorCode.EXECUTION_PROFILE_SOURCE_DRIFT.value,
        ErrorCode.EXECUTION_PROFILE_PROJECT_CONFLICT.value,
        ErrorCode.RESULT_FINALIZATION_NOT_READY.value,
        ErrorCode.RESULT_FINALIZATION_FAILED.value,
        ErrorCode.RESULT_FINALIZATION_CONFLICT.value,
        ErrorCode.RESULT_FINALIZATION_BLOCKED.value,
        ErrorCode.BOUNDARY_PROPOSAL_ALREADY_DECIDED.value,
        ErrorCode.BOUNDARY_PROPOSAL_FINGERPRINT_MISMATCH.value,
        ErrorCode.BOUNDARY_PROPOSAL_SOURCE_STALE.value,
        ErrorCode.BOUNDARY_REVISION_CONFLICT.value,
        ErrorCode.BOUNDARY_MAINTENANCE_REQUIRED.value,
        ErrorCode.BOUNDARY_EFFECT_MAPPING_REQUIRED.value,
        ErrorCode.BOUNDARY_PROPOSAL_PENDING.value,
    }:
        return 409
    if code in {
        ErrorCode.API_NOT_READY.value,
        ErrorCode.API_BINDING_REJECTED.value,
        ErrorCode.SERVE_FAILED.value,
        ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE.value,
        ErrorCode.EXECUTION_PROFILE_STORAGE_FAILED.value,
        ErrorCode.LOCAL_MAINTENANCE_FAILED.value,
        ErrorCode.RUNTIME_REPAIR_FAILED.value,
    }:
        return 503
    if code in {
        ErrorCode.ONBOARDING_READ_BUDGET.value,
        ErrorCode.APPLICATION_ANALYSIS_BUDGET.value,
    }:
        return 413
    if code in {
        ErrorCode.MCP_AUTH_REQUIRED.value,
    }:
        return 401
    if code in {
        ErrorCode.API_CONTROL_REJECTED.value,
        ErrorCode.MCP_PERMISSION_REQUIRED.value,
    }:
        return 403
    if code == ErrorCode.MCP_DISABLED.value:
        return 409
    return 400


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
        from product.backend.infra.runtime.frontend_assets import frontend_asset_identity
        identity = frontend_asset_identity(getattr(request.app.state, 'frontend_dir', None))
        refs = {key:value for key,value in request.path_params.items() if key in {'project_id','candidate_id','suggestion_id'}
            and isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_]{1,96}',value)}
        revision = request.query_params.get('revision')
        if revision is not None and revision.isascii() and revision.isdigit() and len(revision) <= 10:
            refs['revision'] = revision
        details = {'version':__version__, 'frontend_identity':identity, 'validation_error_count':exc.error_count(), **refs}
        logging.getLogger(__name__).error('Internal record validation trace=%s details=%s', request.state.trace_id, details)
        error = JiejianError(ErrorCode.STORAGE_STATE, '界鉴内部记录校验失败，请保留现有要求与材料，并提供本次记录编号', details=details)
        return JSONResponse(status_code=500, content={'schema_version':'1','error':error.to_dict(),'trace_id':request.state.trace_id})
    error = JiejianError(ErrorCode.INPUT_INVALID, "请求参数无效")
    return JSONResponse(
        status_code=422,
        content={
            "schema_version": "1",
            "error": error.to_dict(),
            "trace_id": request.state.trace_id,
        },
    )
