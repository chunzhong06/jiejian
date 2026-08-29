# MCP 访问设置 API：由本地 GUI 显式启停、轮换令牌并管理逐 Project 临时权限。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.mcp_access import MCPAccessController, MCPAccessLevel


class MCPProjectGrantRequest(ApiModel):
    schema_version: Literal["1"]
    level: Literal["READ", "PREPARE", "EXECUTE"]


def build_mcp_access_router(
    context: ApplicationCore,
    access: MCPAccessController,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/mcp/access", response_model=ApiResponse)
    async def get_mcp_access():
        return data_response(access.view().model_dump(mode="json"))

    @router.post("/api/mcp/access/enable", response_model=ApiResponse)
    async def enable_mcp_access():
        return data_response(access.enable().model_dump(mode="json"))

    @router.post("/api/mcp/access/regenerate", response_model=ApiResponse)
    async def regenerate_mcp_access():
        return data_response(access.regenerate().model_dump(mode="json"))

    @router.post("/api/mcp/access/disable", response_model=ApiResponse)
    async def disable_mcp_access():
        return data_response(access.disable().model_dump(mode="json"))

    @router.put(
        "/api/mcp/access/projects/{project_id}",
        response_model=ApiResponse,
    )
    async def set_mcp_project_access(
        project_id: str,
        body: MCPProjectGrantRequest,
    ):
        context.projects.get(project_id)
        return data_response(
            access.set_level(
                project_id,
                MCPAccessLevel(body.level),
            ).model_dump(mode="json")
        )

    return router


__all__ = ["build_mcp_access_router"]
