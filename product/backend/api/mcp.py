# =============================================================================
# MCP Streamable HTTP 当前检查与变化控制入口
#
# 职责
#   复用 ApplicationCore 读取事实、登记变化和提交或取消完整检查。
#
# 边界
#   临时项目授权不能变成权限 writer，不构造 LOCAL_GUI approval 或允许客户端裁剪考题。
# =============================================================================

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

from mcp import MCPError
from mcp.server import MCPServer
from mcp.server.context import HandlerResult, ServerRequestContext
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from product.backend import __version__
from product.backend.composition import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.diagnostics import runtime_environment_details
from product.backend.workflows.mcp_access import MCPAccessController, MCPAccessLevel


_T = TypeVar("_T")
_ACCESS_ERROR_CODES = {
    ErrorCode.MCP_DISABLED.value: -32041,
    ErrorCode.MCP_AUTH_REQUIRED.value: -32042,
    ErrorCode.MCP_PERMISSION_REQUIRED.value: -32043,
}


def _recovery_for(code: str) -> str:
    return {
        ErrorCode.MCP_DISABLED.value: "请在界鉴的“AI 工具连接”面板中启用连接后重试。",
        ErrorCode.MCP_AUTH_REQUIRED.value: "请从当前界鉴进程复制新的 Bearer 令牌后重试。",
        ErrorCode.MCP_PERMISSION_REQUIRED.value: "请在界鉴中为该应用明确提升临时权限后重试。",
    }.get(code, "请回到界鉴查看当前应用状态并按页面提示恢复。")


def _as_mcp_error(exc: JiejianError) -> MCPError:
    payload = exc.to_dict()
    return MCPError(
        code=_ACCESS_ERROR_CODES.get(exc.code, -32010),
        message=str(payload["message"]),
        data={
            "error_code": exc.code,
            "details": payload.get("details", {}),
            "recovery": _recovery_for(exc.code),
        },
    )


def require_mcp_level(
    access: MCPAccessController,
    ctx: Context,
    required_level: MCPAccessLevel,
    *,
    project_id: str | None = None,
) -> None:
    """每次调用都重新校验 Bearer 与当前 Project 授权。"""

    headers: Mapping[str, str] = ctx.headers or {}
    try:
        access.require(headers.get("authorization"), required_level, project_id=project_id)
    except JiejianError as exc:
        raise _as_mcp_error(exc) from None


def _invoke(operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except JiejianError as exc:
        raise _as_mcp_error(exc) from None


def _json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, tuple | list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    return value


def _understanding_view(value: BaseModel) -> dict[str, Any]:
    payload = value.model_dump(mode="json")
    for field in ("source_root", "source_fingerprint", "endpoint_source_fingerprint"):
        payload.pop(field, None)
    for field in ("role_candidates", "action_candidates"):
        for candidate in payload.get(field, []):
            candidate.pop("evidence", None)
    return payload


def _current_change_view(value):
    """Agent 仅看到相对路径与业务影响，不得到源码、快照或配置指纹。"""
    return dict(project_id=value.manifest.project_id,change_id=value.manifest.change_id,reason=value.manifest.reason,
        submitted_by=value.manifest.submitted_by,claimed_paths=list(value.manifest.claimed_paths),
        registration_status="RECORDED", repair_reference=_json(value.manifest.repair_reference),
        comparison_status=value.change_set.status,
        receipt_boundary="登记回执只确认本批修改已记录，不确认修复成功；无需让用户重复登记。",
        added_paths=list(value.change_set.added_paths),modified_paths=list(value.change_set.modified_paths),
        removed_paths=list(value.change_set.removed_paths),revalidation=_json(value.revalidation),
        action_impacts=[dict(action_id=item.action_id,action_revision=item.action_revision,classification=item.classification,
            permission_ids=[ref.intent_id for ref in item.permission_refs],relevant_paths=list(item.relevant_paths))
            for item in value.assessment.payload.action_impacts])


def _current_run_view(value):
    return dict(run_id=value.run.run_id,project_id=value.run.project_id,lifecycle=value.run.lifecycle,
        verdict=value.run.verdict,result_integrity=value.result_integrity,job=_json(value.job),progress=_json(value.progress))


def _current_repair_view(contract):
    from product.backend.workflows.checks.repair_text import REPAIR_REQUIREMENTS
    return dict(reference=_json(contract.reference()),requirements=dict(REPAIR_REQUIREMENTS),
        permission=_json(contract.deny.identity.permission),resource_id=contract.deny.identity.resource_id,
        resource_owner_test_identity_id=contract.deny.identity.resource_owner_test_identity_id,
        must_disappear=list(contract.deny.identity.protected_effect_ids),evidence_refs=list(contract.deny.evidence_refs),
        selected_allow_permission=_json(contract.selected_control.identity.permission),
        must_preserve=[dict(role=role,source_case_id=item.source_case_id,
            action_id=item.identity.action_id,protected_effect_ids=list(item.identity.protected_effect_ids))
            for role,item in (("SELECTED_ALLOW",contract.selected_control),
                             *(("REGRESSION",row) for row in contract.regressions))],
        regression_count=len(contract.regressions))


def _current_story_view(story):
    return dict(run_id=story.run_id,project_id=story.project_id,verdict=story.verdict,judgement=story.judgement,
        actions=[dict(case_id=item.case_id,display_name=item.display_name,judgement=item.judgement,
            permission_expectation=item.permission.expectation,fact_comparison=_json(item.fact_comparison),
            breakpoint=None if item.breakpoint is None else dict(breakpoint_type=item.breakpoint.breakpoint_type,precision=item.breakpoint.precision),
            repair_requirement=None if item.repair_requirement is None else _current_repair_view(item.repair_requirement),
            claim_boundary=list(item.claim_boundary)) for item in story.actions],repair_verification=_json(story.repair_verification))


class MCPBearerGuard:
    """在 SDK 解析正文前只接受当前进程签发的 Bearer。"""

    def __init__(self, app: ASGIApp, access: MCPAccessController) -> None:
        self._app = app
        self._access = access

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        try:
            self._access.authorize(Headers(scope=scope).get("authorization"))
        except JiejianError as exc:
            payload = exc.to_dict()
            payload["recovery"] = _recovery_for(exc.code)
            response = JSONResponse(
                status_code=401 if exc.code == ErrorCode.MCP_AUTH_REQUIRED.value else 403,
                content={"schema_version": "1", "error": payload},
                headers={"WWW-Authenticate": "Bearer"} if exc.code == ErrorCode.MCP_AUTH_REQUIRED.value else None,
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)


class MCPPathAdapter:
    """把 FastAPI 的精确 /mcp 挂载适配为 SDK 子应用根路径。"""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        adapted = dict(scope)
        adapted["root_path"] = f"{scope.get('root_path', '')}/mcp"
        adapted["path"] = "/"
        adapted["raw_path"] = b"/"
        await self._app(adapted, receive, send)


@dataclass(frozen=True, slots=True)
class MCPControl:
    server: MCPServer
    app: ASGIApp


class _CurrentMCPServer(MCPServer):
    async def list_tools(self):
        # 公布的参数schema与下方middleware的额外字段拒绝规则保持一致。
        return [item.model_copy(update={"input_schema": {**item.input_schema, "additionalProperties": False}})
            for item in await super().list_tools()]


def build_mcp_control(
    context: ApplicationCore,
    access: MCPAccessController,
    *,
    control_origin: str,
    control_host: str,
) -> MCPControl:
    """注册精确分级工具集，并绑定当前 loopback origin。"""

    async def record_client_activity(
        request: ServerRequestContext[Any, Any],
        call_next: Callable[[ServerRequestContext[Any, Any]], Any],
    ) -> HandlerResult:
        # SDK 的默认参数模型会忽略额外字段；按已发布 schema 拒绝它们，避免选择参数被静默吞掉。
        if request.method == "tools/call" and request.params is not None:
            arguments = request.params.get("arguments") or {}
            tool = next((item for item in await server.list_tools() if item.name == request.params.get("name")), None)
            if tool is not None and isinstance(arguments, Mapping) and set(arguments) - set(tool.input_schema.get("properties", {})):
                raise _as_mcp_error(JiejianError(ErrorCode.STATE_PRECONDITION, "MCP 工具包含未声明参数"))
        result = await call_next(request)
        params = request.session.client_params
        access.note_activity(
            None if params is None else params.client_info.name,
            None if params is None else params.client_info.version,
        )
        return result

    server = _CurrentMCPServer(
        "界鉴 JIEJIAN",
        description="界鉴本地权限检查与代码变化协作入口；权限规则只能由本机GUI批准。",
        instructions=(
            "READ读取既有事实；PREPARE只登记代码变化声明，界鉴重新核对实际源码；"
            "EXECUTE按完整当前权限运行检查或取消本项目检查；需要人类决定时返回界鉴，不修改权限或检查结论。"
        ),
        version=__version__,
        middleware=[record_client_activity],
    )

    @server.tool(name="jiejian_project_list", structured_output=True)
    def project_list(ctx: Context, include_archived: bool = False) -> list[dict[str, Any]]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ)
        return _json(_invoke(lambda: context.projects.list(include_archived=include_archived)))

    @server.tool(name="jiejian_project_show", structured_output=True)
    def project_show(ctx: Context, project_id: str) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.projects.get(project_id)))

    @server.tool(name="jiejian_application_understanding", structured_output=True)
    def application_understanding(ctx: Context, project_id: str) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _understanding_view(_invoke(lambda: context.application_understanding.get(project_id)))

    @server.tool(name="jiejian_business_boundary", structured_output=True)
    def business_boundary(ctx: Context, project_id: str) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.business_boundaries.view(project_id)))

    @server.tool(name="jiejian_intent_show", structured_output=True)
    def intent_show(ctx: Context, project_id: str, intent_id: str) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.permission_intents.history(project_id, intent_id)))

    @server.tool(name="jiejian_identity_list", structured_output=True)
    def identity_list(ctx: Context, project_id: str) -> list[dict[str, Any]]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.test_identities.list(project_id)))

    @server.tool(name="jiejian_system_status", structured_output=True)
    def system_status(ctx: Context) -> dict[str, Any]:
        require_mcp_level(access, ctx, MCPAccessLevel.READ)
        environment = runtime_environment_details()
        return {
            "schema_version": "1",
            "version": __version__,
            "api": "available",
            **context.worker_status(),
            "browser": environment["playwright"]["status"],
        }

    @server.tool(name="jiejian_change_show",structured_output=True)
    def change_show(ctx: Context, project_id: str, change_id: str | None = None) -> dict[str,Any]:
        require_mcp_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        value = _invoke(lambda:context.source_changes.latest(project_id) if change_id is None else context.source_changes.view(project_id,change_id))
        return {"change":None if value is None else _current_change_view(value)}

    @server.tool(name="jiejian_check_status",structured_output=True)
    def check_status(ctx: Context, project_id: str, run_id: str | None = None) -> dict[str,Any]:
        require_mcp_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        if run_id is not None:
            return _current_run_view(_invoke(lambda:context.check_results.status(run_id,project_id=project_id)))
        preview = _invoke(lambda:context.checks.preview(project_id))
        return {"project_id":project_id,"can_execute":preview.can_execute,"action_count":preview.action_count,
            "case_count":preview.case_count,"gaps":_json(preview.gaps)}

    @server.tool(name="jiejian_result_show",structured_output=True)
    def result_show(ctx: Context, project_id: str, run_id: str) -> dict[str,Any]:
        require_mcp_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        _invoke(lambda:context.check_results.status(run_id,project_id=project_id))
        return _current_story_view(_invoke(lambda:context.check_story.build(run_id)))

    @server.tool(name="jiejian_repair_show",structured_output=True)
    def repair_show(ctx: Context, project_id: str, source_run_id: str | None = None, source_case_id: str | None = None) -> dict[str,Any]:
        require_mcp_level(access,ctx,MCPAccessLevel.READ,project_id=project_id)
        if source_run_id is not None:
            _invoke(lambda:context.check_results.status(source_run_id,project_id=project_id))
            values = _invoke(lambda:context.check_repairs.contracts(source_run_id))
            return {"requirements":[_current_repair_view(item) for item in values if source_case_id is None or item.source_case_id==source_case_id]}
        if source_case_id is not None:
            raise _as_mcp_error(JiejianError(ErrorCode.STATE_PRECONDITION,"指定原题需要源检查引用"))
        value = _invoke(lambda:context.project_repair.evaluate(project_id))
        return {"project_id":project_id,"status":value.status,"tasks":[{"status":item.status,"change_id":item.change_id,
            "run_id":item.run_id,"requirement":_current_repair_view(item.contract)} for item in value.tasks]}

    @server.tool(name="jiejian_change_submit",structured_output=True)
    def change_submit(ctx: Context, project_id: str, reason: str, claimed_paths: list[str] | None = None,
        repair_reference: dict[str,str] | None = None) -> dict[str,Any]:
        require_mcp_level(access,ctx,MCPAccessLevel.PREPARE,project_id=project_id)
        name = access.view().client_name
        submitted_by = "MCP Agent" if name is None else "MCP · "+name[:122]
        return _current_change_view(_invoke(lambda:context.source_changes.submit(project_id,reason=reason,
            claimed_paths=claimed_paths or (),repair_reference=repair_reference,submitted_by=submitted_by)))

    @server.tool(name="jiejian_check_run",structured_output=True)
    def check_run(ctx: Context, project_id: str, idempotency_key: str, change_id: str | None = None) -> dict[str,Any]:
        require_mcp_level(access,ctx,MCPAccessLevel.EXECUTE,project_id=project_id)
        preview = _invoke(lambda:context.checks.preview(project_id,change_id=change_id))
        submitted = _invoke(lambda:context.checks.submit(project_id,expected_plan_fingerprint=preview.plan_fingerprint,
            idempotency_key=idempotency_key,change_id=change_id))
        return _current_run_view(_invoke(lambda:context.check_results.status(submitted.run.run_id,project_id=project_id)))

    @server.tool(name="jiejian_check_cancel",structured_output=True)
    def check_cancel(ctx: Context, project_id: str, run_id: str) -> dict[str,Any]:
        require_mcp_level(access,ctx,MCPAccessLevel.EXECUTE,project_id=project_id)
        _invoke(lambda:context.checks.cancel(project_id,run_id))
        return _current_run_view(_invoke(lambda:context.check_results.status(run_id,project_id=project_id)))

    sdk_app = server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[control_host],
            allowed_origins=[control_origin],
        ),
        host="127.0.0.1",
    )
    return MCPControl(server=server, app=MCPPathAdapter(MCPBearerGuard(sdk_app, access)))


__all__ = [
    "MCPBearerGuard", "MCPControl", "MCPPathAdapter", "build_mcp_control", "require_mcp_level",
]
