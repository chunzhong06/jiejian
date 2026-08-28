# API 错误映射
# 将内部稳定错误转换为脱敏 HTTP envelope；原始异常细节不得越过此边界。

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.assistant.diagnosis import ErrorDiagnosisContext, diagnose_error


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
        ErrorCode.LLM_PROFILE_NOT_FOUND.value,
        ErrorCode.EXECUTION_PROFILE_NOT_FOUND.value,
        ErrorCode.RESULT_FINALIZATION_NOT_FOUND.value,
    }:
        return 404
    if code in {
        ErrorCode.PROJECT_SOURCE_DRIFT.value,
        ErrorCode.PROJECT_NOT_REVALIDATED.value,
        ErrorCode.PROJECT_ARCHIVE_CONFLICT.value,
        ErrorCode.APPLICATION_REVISION_CONFLICT.value,
        ErrorCode.APPLICATION_CANDIDATE_CONFLICT.value,
        ErrorCode.CONTRACT_NOT_ACTIVE.value,
        ErrorCode.JOB_CANCEL_CONFLICT.value,
        ErrorCode.JOB_TERMINAL_CONFLICT.value,
        ErrorCode.LLM_TEST_IN_PROGRESS.value,
        ErrorCode.EXECUTION_PROFILE_SOURCE_DRIFT.value,
        ErrorCode.EXECUTION_PROFILE_PROJECT_CONFLICT.value,
        ErrorCode.RESULT_FINALIZATION_NOT_READY.value,
        ErrorCode.RESULT_FINALIZATION_FAILED.value,
        ErrorCode.RESULT_FINALIZATION_CONFLICT.value,
        ErrorCode.RESULT_FINALIZATION_BLOCKED.value,
    }:
        return 409
    if code in {
        ErrorCode.API_NOT_READY.value,
        ErrorCode.API_BINDING_REJECTED.value,
        ErrorCode.SERVE_FAILED.value,
        ErrorCode.LLM_PROVIDER_UNAVAILABLE.value,
        ErrorCode.LLM_PROVIDER_UNAVAILABLE_WIRE.value,
        ErrorCode.LLM_SECRET_UNAVAILABLE.value,
        ErrorCode.LLM_PROFILE_STORAGE_FAILED.value,
        ErrorCode.ONBOARDING_SELECTOR_UNAVAILABLE.value,
        ErrorCode.EXECUTION_PROFILE_STORAGE_FAILED.value,
    }:
        return 503
    if code in {
        ErrorCode.ONBOARDING_READ_BUDGET.value,
        ErrorCode.APPLICATION_ANALYSIS_BUDGET.value,
    }:
        return 413
    if code == ErrorCode.LLM_AUTH_FAILED.value:
        return 401
    if code == ErrorCode.LLM_RATE_LIMITED.value:
        return 429
    if code == ErrorCode.LLM_TIMEOUT.value:
        return 504
    if code == ErrorCode.LLM_INVALID_RESPONSE.value:
        return 502
    if code == ErrorCode.API_CONTROL_REJECTED.value:
        return 403
    return 400


async def jiejian_error_handler(request: Request, exc: JiejianError) -> JSONResponse:
    error = exc.to_dict()
    error["diagnosis"] = diagnose_error(
        ErrorDiagnosisContext(error_code=exc.code)
    ).model_dump(mode="json")
    return JSONResponse(
        status_code=_status_for(exc.code),
        content={
            "schema_version": "1",
            "error": error,
            "trace_id": request.state.trace_id,
        },
    )


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    error = JiejianError(ErrorCode.INPUT_INVALID, "请求参数无效")
    return JSONResponse(
        status_code=422,
        content={
            "schema_version": "1",
            "error": error.to_dict(),
            "trace_id": request.state.trace_id,
        },
    )


async def validation_error_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    error = JiejianError(ErrorCode.INPUT_INVALID, "请求参数无效")
    return JSONResponse(
        status_code=422,
        content={
            "schema_version": "1",
            "error": error.to_dict(),
            "trace_id": request.state.trace_id,
        },
    )
