# 官方体验只读状态：完整 Sample 运行链暂不注册，公开合同由 Boundary API 提供。

from __future__ import annotations

from fastapi import APIRouter

from product.backend.api.envelope import ApiResponse, data_response


def build_current_experience_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/experience/official-sample", response_model=ApiResponse)
    def official_sample_status():
        return data_response(
            {
                "available": False,
                "display_name": "协作空间",
                "unavailable_reason": "完整检查体验将在新业务边界主链接入后恢复",
                "active": False,
                "experience_id": None,
                "project_id": None,
                "origin": None,
                "scenario_prepared": False,
                "scenario_version": None,
                "scenario_changed_at_us": None,
                "vulnerable_change_id": None,
                "repair_change_id": None,
            }
        )

    @router.get(
        "/api/experience/official-sample/validation-summary",
        response_model=ApiResponse,
    )
    def official_sample_validation_summary():
        return data_response(
            {
                "available": False,
                "unavailable_reason": "当前不运行 validation 或 competition",
                "summary": None,
            }
        )

    return router


__all__ = ["build_current_experience_router"]
