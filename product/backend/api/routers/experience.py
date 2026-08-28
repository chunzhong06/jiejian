# 官方体验 API：只解析小型产品请求并调用 Experience workflow，不承载 Sample 或安全判断。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.official_sample import OfficialExperienceMode


def build_experience_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/experience/official-sample", response_model=ApiResponse)
    def official_sample_status():
        return data_response(context.official_experience.status().model_dump(mode="json"))

    @router.post("/api/experience/official-sample/start", response_model=ApiResponse)
    def start_official_sample(body: OfficialSampleStartRequest):
        return data_response(
            context.official_experience.start(
                OfficialExperienceMode(body.experience_mode),
                consent=body.consent,
            ).model_dump(mode="json")
        )

    @router.post(
        "/api/experience/official-sample/identities",
        response_model=ApiResponse,
    )
    def prepare_official_sample_identities():
        return data_response(
            context.official_experience.prepare_identities().model_dump(mode="json")
        )

    @router.post(
        "/api/experience/official-sample/behavior",
        response_model=ApiResponse,
    )
    def switch_official_sample_behavior(body: OfficialSampleBehaviorRequest):
        return data_response(
            context.official_experience.switch_behavior(
                authorization_order=body.authorization_order,
                blob_observation=body.blob_observation,
                verification_run_id=body.verification_run_id,
            ).model_dump(mode="json")
        )

    @router.post("/api/experience/official-sample/stop", response_model=ApiResponse)
    def stop_official_sample():
        return data_response(context.official_experience.stop().model_dump(mode="json"))

    return router


class OfficialSampleStartRequest(ApiModel):
    schema_version: Literal["1"]
    experience_mode: Literal["GUIDED", "FULL"]
    consent: Literal[True]


class OfficialSampleBehaviorRequest(ApiModel):
    schema_version: Literal["1"]
    authorization_order: Literal[
        "ENQUEUE_BEFORE_AUTHORIZE",
        "AUTHORIZE_BEFORE_ENQUEUE",
    ]
    blob_observation: Literal["AVAILABLE", "UNAVAILABLE"]
    verification_run_id: str | None = Field(
        default=None,
        pattern=r"^run_[0-9a-f]{32}$",
    )


__all__ = ["build_experience_router"]
