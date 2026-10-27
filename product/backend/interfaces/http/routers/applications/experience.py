# 官方体验 API：只解析小型产品请求并调用 Experience workflow，不承载 Sample 或安全判断。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query

from product.backend.interfaces.http.envelope import ApiModel, ApiResponse, data_response
from product.backend.bootstrap import ApplicationCore
from product.backend.application.examples.environment import OfficialScenarioVersion
from product.backend.domain.checks.repair import CurrentRepairReference
from product.backend.domain.errors import ErrorCode, JiejianError


def build_experience_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/experience/official-sample", response_model=ApiResponse)
    def official_sample_status(lightweight: bool = False, operation_id: str | None = None):
        service=context.official_experience
        if hasattr(service,'operation_view'):
            value=service.operation_view(operation_id,lightweight=lightweight) if operation_id else service.status(lightweight=lightweight)
        else:value=service.status()
        return data_response(value.model_dump(mode="json"))

    @router.get("/api/experience/official-sample/history", response_model=ApiResponse)
    def official_sample_history(limit: int = Query(25, ge=1, le=100)):
        return data_response(context.official_experience.history(limit=limit))

    @router.get("/api/experience/official-sample/development", response_model=ApiResponse)
    def official_development():
        return data_response(context.official_experience.development_journey().model_dump(mode="json"))

    @router.post("/api/experience/official-sample/observation", response_model=ApiResponse)
    def official_observation(body: OfficialObservationRequest):
        return data_response(context.official_experience.set_observation(available=body.available).model_dump(mode="json"))

    @router.get(
        "/api/experience/official-sample/validation-summary",
        response_model=ApiResponse,
    )
    def official_sample_validation_summary():
        return data_response(
            {"available": False, "unavailable_reason": "当前不运行 validation 或 competition", "summary": None}
        )

    @router.post("/api/experience/official-sample/start", response_model=ApiResponse)
    def start_official_sample(body: OfficialSampleStartRequest):
        service=context.official_experience
        asynchronous=hasattr(service,'prepare_step')
        value=service.start(consent=body.consent,operation_id=body.operation_id,**({'wait':False} if asynchronous else {}))
        return data_response(value.model_dump(mode='json'),status_code=202 if asynchronous else 200)

    @router.post('/api/experience/official-sample/resume',response_model=ApiResponse)
    def resume_official_sample(body: OfficialSampleStartRequest):
        if not hasattr(context.official_experience,'resume'):
            raise JiejianError(ErrorCode.STATE_PRECONDITION,'当前示例提供方不支持继续上次实例')
        return data_response(context.official_experience.resume(consent=body.consent,operation_id=body.operation_id,wait=False).model_dump(mode='json'),status_code=202)

    @router.post("/api/experience/official-sample/reset", response_model=ApiResponse)
    def reset_official_sample(body: OfficialSampleStartRequest):
        service=context.official_experience
        asynchronous=hasattr(service,'prepare_step')
        value=service.reset(consent=body.consent,operation_id=body.operation_id,**({'wait':False} if asynchronous else {}))
        return data_response(value.model_dump(mode='json'),status_code=202 if asynchronous else 200)

    @router.post("/api/experience/official-sample/reconcile", response_model=ApiResponse)
    def reconcile_official_sample():
        return data_response(context.official_experience.reconcile().model_dump(mode="json"))

    @router.post(
        "/api/experience/official-sample/prepare",
        response_model=ApiResponse,
    )
    def prepare_official_sample():
        return data_response(
            context.official_experience.prepare().model_dump(mode="json")
        )

    @router.post("/api/experience/official-sample/boundary-proposal", response_model=ApiResponse)
    def official_boundary_proposal(body: OfficialBoundaryChoice | None = None):
        options={} if context.official_samples.installation.runtime_kind=='PYTHON' else {'exhibition_download':None if body is None else body.exhibition_download}
        return data_response(context.official_experience.boundary_proposal(**options).model_dump(mode="json"))

    @router.post(
        "/api/experience/official-sample/version",
        response_model=ApiResponse,
    )
    def switch_official_sample_version(body: OfficialSampleVersionRequest):
        return data_response(
            context.official_experience.switch_version(
                version=OfficialScenarioVersion(body.version),
                repair_reference=body.repair_reference,
            ).model_dump(mode="json")
        )

    @router.post("/api/experience/official-sample/stop", response_model=ApiResponse)
    def stop_official_sample(body: OfficialSampleStopRequest | None = None):
        return data_response(context.official_experience.stop(operation_id=None if body is None else body.operation_id).model_dump(mode="json"))

    return router


class OfficialSampleStartRequest(ApiModel):
    schema_version: Literal["1"]
    consent: Literal[True]
    operation_id: str | None = None


class OfficialSampleStopRequest(ApiModel):
    operation_id: str | None = None


class OfficialSampleVersionRequest(ApiModel):
    schema_version: Literal["1"]
    version: Literal["VULNERABLE", "EVIDENCE_LIMITED", "FIXED", "EXPOSE_REVOKE", "PREVIEW_CHANGED"]
    repair_reference: CurrentRepairReference | None = None


class OfficialBoundaryChoice(ApiModel):
    exhibition_download: bool


class OfficialObservationRequest(ApiModel):
    schema_version: Literal["1"]
    available: bool


__all__ = ["build_experience_router"]
