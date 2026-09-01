# MCP 访问设置 API：由本地 GUI 显式配对、管理凭据并控制逐 Project 临时权限。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.composition import ApplicationCore
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

    @router.post("/api/mcp/access/pair", response_model=ApiResponse)
    async def pair_mcp_access():
        return data_response(access.pair().model_dump(mode="json"))

    @router.post("/api/mcp/access/reveal", response_model=ApiResponse)
    async def reveal_mcp_access():
        return data_response(access.reveal().model_dump(mode="json"))

    @router.post("/api/mcp/access/rotate", response_model=ApiResponse)
    async def rotate_mcp_access():
        return data_response(access.rotate().model_dump(mode="json"))

    @router.post("/api/mcp/access/resume", response_model=ApiResponse)
    async def resume_mcp_access():
        return data_response(access.resume().model_dump(mode="json"))

    @router.post("/api/mcp/access/pause", response_model=ApiResponse)
    async def pause_mcp_access():
        return data_response(access.pause().model_dump(mode="json"))

    @router.post("/api/mcp/access/forget", response_model=ApiResponse)
    async def forget_mcp_access():
        return data_response(access.forget().model_dump(mode="json"))

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
