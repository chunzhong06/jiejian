# 官方体验 API：只解析小型产品请求并调用 Experience workflow，不承载 Sample 或安全判断。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.composition import ApplicationCore
from product.backend.workflows.official_sample import OfficialScenarioVersion


def build_experience_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/experience/official-sample", response_model=ApiResponse)
    def official_sample_status():
        return data_response(context.official_experience.status().model_dump(mode="json"))

    @router.get(
        "/api/experience/official-sample/validation-summary",
        response_model=ApiResponse,
    )
    def official_sample_validation_summary():
        return data_response(
            context.competition_validation.get().model_dump(mode="json")
        )

    @router.post("/api/experience/official-sample/start", response_model=ApiResponse)
    def start_official_sample(body: OfficialSampleStartRequest):
        return data_response(
            context.official_experience.start(
                consent=body.consent,
            ).model_dump(mode="json")
        )

    @router.post(
        "/api/experience/official-sample/prepare",
        response_model=ApiResponse,
    )
    def prepare_official_sample():
        return data_response(
            context.official_experience.prepare().model_dump(mode="json")
        )

    @router.post(
        "/api/experience/official-sample/version",
        response_model=ApiResponse,
    )
    def switch_official_sample_version(body: OfficialSampleVersionRequest):
        return data_response(
            context.official_experience.switch_version(
                version=OfficialScenarioVersion(body.version),
                source_run_id=body.source_run_id,
            ).model_dump(mode="json")
        )

    @router.post("/api/experience/official-sample/stop", response_model=ApiResponse)
    def stop_official_sample():
        return data_response(context.official_experience.stop().model_dump(mode="json"))

    return router


class OfficialSampleStartRequest(ApiModel):
    schema_version: Literal["1"]
    consent: Literal[True]


class OfficialSampleVersionRequest(ApiModel):
    schema_version: Literal["1"]
    version: Literal["VULNERABLE", "EVIDENCE_LIMITED", "FIXED"]
    source_run_id: str | None = Field(
        default=None,
        pattern=r"^run_[0-9a-f]{32}$",
    )


__all__ = ["build_experience_router"]
