# MCP 访问设置 API：由本地 GUI 显式配对、管理凭据并控制逐 Project 临时权限。

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from product.backend.api.envelope import ApiModel, ApiResponse, data_response
from product.backend.composition import ApplicationCore
from product.backend.workflows.agent_access.service import MCPAccessController, MCPAccessLevel
from product.backend.workflows.agent_access.connections import AgentConnections
from pydantic import Field

ClientName = Literal['dsh', 'codex', 'zcode', 'trae', 'codebuddy', 'qoder']


class ClientConnectRequest(ApiModel):
    profile: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_.-]{1,80}$')


class MCPProjectGrantRequest(ApiModel):
    schema_version: Literal["1"]
    level: Literal["READ", "PREPARE", "EXECUTE"]


def build_mcp_access_router(
    context: ApplicationCore,
    access: MCPAccessController,
    connections: AgentConnections,
) -> APIRouter:
    router = APIRouter()

    @router.post('/api/mcp/clients/{client}/connect', response_model=ApiResponse)
    def connect_client(client: ClientName, body: ClientConnectRequest):
        return data_response(connections.install(client, body.profile))

    @router.get('/api/mcp/clients/{client}', response_model=ApiResponse)
    def client_status(client: ClientName):
        return data_response(connections.status(client))

    @router.post('/api/mcp/clients/{client}/restore', response_model=ApiResponse)
    def restore_client(client: ClientName):
        return data_response(connections.restore(client))

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
