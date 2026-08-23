# =============================================================================
# Regression Gate Baseline/Gate HTTP 适配器
#
# API 只负责请求校验和统一应用服务调用，不复制门禁策略。
# =============================================================================

from __future__ import annotations

from fastapi import APIRouter

from product.backend.workflows.context import ApplicationCore
from product.backend.api.envelope import data_response
from product.backend.api.envelope import ApiResponse


def build_gating_router(context: ApplicationCore) -> APIRouter:
    router = APIRouter()

    @router.post("/api/projects/{project_id}/baselines", response_model=ApiResponse)
    async def accept_baseline(project_id: str, request: BaselineAcceptRequest):
        result = context.gating.accept_baseline(
            request.accepted_run_id,
            actor=request.actor,
            reason=request.reason,
            expected_project_id=project_id,
        )
        return data_response(result)

    @router.get("/api/baselines/{baseline_id}", response_model=ApiResponse)
    async def get_baseline(baseline_id: str):
        return data_response(context.gating.get_baseline(baseline_id))

    @router.post("/api/baselines/{baseline_id}/runs/{run_id}/gate", response_model=ApiResponse)
    async def evaluate_gate(baseline_id: str, run_id: str, request: GateEvaluateRequest):
        from product.backend.core.verification.gating import GatePolicy

        return data_response(
            context.gating.evaluate(
                baseline_id,
                run_id,
                policy=GatePolicy(minimum_severity=request.minimum_severity),
            )
        )

    @router.get("/api/baselines/{baseline_id}/runs/{run_id}/gate", response_model=ApiResponse)
    async def get_latest_gate(baseline_id: str, run_id: str):
        return data_response(context.gating.latest_gate_result(baseline_id, run_id))

    @router.get("/api/gates/{gate_result_id}", response_model=ApiResponse)
    async def get_gate(gate_result_id: str):
        return data_response(context.gating.get_gate_result(gate_result_id))

    return router

# Regression Gate API 请求边界；策略和操作者输入严格版本化。

from typing import Literal

from pydantic import Field, field_validator

from product.backend.api.envelope import ApiModel


class BaselineAcceptRequest(ApiModel):
    schema_version: Literal["1"]
    accepted_run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    actor: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=1024)

    @field_validator("actor", "reason")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("actor and reason must be non-empty")
        return value.strip()


class GateEvaluateRequest(ApiModel):
    schema_version: Literal["1"]
    minimum_severity: Literal["low", "medium", "high", "critical"] = "low"
