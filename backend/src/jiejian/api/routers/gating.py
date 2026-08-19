# =============================================================================
# 阶段 7.2 Baseline/Gate v2 HTTP 适配器
#
# API 只负责请求校验和统一应用服务调用，不复制门禁策略。
# =============================================================================

from __future__ import annotations

from fastapi import APIRouter

from ...application.context import ApplicationContext
from ..responses import data_response
from ..schemas.common import ApiResponse
from ..schemas.gating import BaselineAcceptRequest, GateEvaluateRequest


def build_gating_router(context: ApplicationContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v2/projects/{project_id}/baselines", response_model=ApiResponse)
    async def accept_baseline(project_id: str, request: BaselineAcceptRequest):
        result = context.gating.accept_baseline(
            request.accepted_run_id,
            actor=request.actor,
            reason=request.reason,
            expected_project_id=project_id,
        )
        return data_response(result)

    @router.get("/api/v2/baselines/{baseline_id}", response_model=ApiResponse)
    async def get_baseline(baseline_id: str):
        return data_response(context.gating.get_baseline(baseline_id))

    @router.post("/api/v2/baselines/{baseline_id}/runs/{run_id}/gate", response_model=ApiResponse)
    async def evaluate_gate(baseline_id: str, run_id: str, request: GateEvaluateRequest):
        from ...verification.gating import GatePolicy

        return data_response(
            context.gating.evaluate(
                baseline_id,
                run_id,
                policy=GatePolicy(minimum_severity=request.minimum_severity),
            )
        )

    @router.get("/api/v2/baselines/{baseline_id}/runs/{run_id}/gate", response_model=ApiResponse)
    async def get_latest_gate(baseline_id: str, run_id: str):
        return data_response(context.gating.latest_gate_result(baseline_id, run_id))

    @router.get("/api/v2/gates/{gate_result_id}", response_model=ApiResponse)
    async def get_gate(gate_result_id: str):
        return data_response(context.gating.get_gate_result(gate_result_id))

    return router
