# =============================================================================
# MCP Streamable HTTP 控制入口
#
# 定位
#   官方 MCP Python SDK 与界鉴唯一 ApplicationCore 之间的本地 ASGI 适配层。
#
# 职责
#   挂载固定工具白名单｜统一校验 Bearer 与逐 Project 等级｜只读投影修复要求与其他非秘密事实。
#
# 边界
#   不创建第二个 Core、Worker 或服务进程；不返回源码、补丁建议、请求正文、环境变量、完整日志或完整 Evidence。
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

from mcp import MCPError
from mcp.server import MCPServer
from mcp.server.context import HandlerResult, ServerRequestContext
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from product.backend import __version__
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.permission_intent import (
    PermissionIntentEffectiveState,
    PermissionIntentRelation,
    PermissionIntentSemantic,
    ProtectedEffect,
)
from product.backend.core.repair import RepairContractReference
from product.backend.core.verification.permissions import (
    PermissionExpectation,
    SecurityEffectKind,
)
from product.backend.infra.runtime.diagnostics import runtime_environment_details
from product.backend.infra.runtime.jobs.models import RequestCancellation
from product.backend.infra.runtime.worker.supervisor import LocalWorkerSupervisor
from product.backend.workflows.context import ApplicationCore
from product.backend.workflows.mcp_access import MCPAccessController, MCPAccessLevel
from product.backend.workflows.official_sample import OfficialExperienceMode


_T = TypeVar("_T")
_ACCESS_ERROR_CODES = {
    ErrorCode.MCP_DISABLED.value: -32041,
    ErrorCode.MCP_AUTH_REQUIRED.value: -32042,
    ErrorCode.MCP_PERMISSION_REQUIRED.value: -32043,
}


class MCPProtectedEffectInput(BaseModel):
    """MCP 建议中的业务效果，不接受 Observer、HTTP 或任意扩展字段。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "STATE_MUTATION",
        "DATA_DISCLOSURE",
        "OBJECT_CREATION",
        "EXTERNAL_DISPATCH",
        "RESTRICTED_FUNCTION_INVOCATION",
        "CREDENTIAL_ACCESS",
    ]
    resource_type: str = Field(min_length=1, max_length=128)
    business_label: str = Field(min_length=1, max_length=256)
    protected_fields: tuple[str, ...] = Field(default=(), max_length=64)

    def to_domain(self) -> ProtectedEffect:
        return ProtectedEffect(
            kind=SecurityEffectKind(self.kind),
            resource_type=self.resource_type,
            business_label=self.business_label,
            protected_fields=self.protected_fields,
        )


class MCPPermissionIntentSemanticInput(BaseModel):
    """把 Agent 的有界业务建议显式转换为严格 Ledger 语义。"""

    model_config = ConfigDict(extra="forbid")

    effective_state: Literal["ACTIVE", "RETIRED"]
    subject_display_name: str = Field(min_length=1, max_length=128)
    action_display_name: str = Field(min_length=1, max_length=256)
    resource_owner_display_name: str = Field(min_length=1, max_length=128)
    relation: Literal["OWNS", "SAME_ROLE_OTHER_ACCOUNT", "OTHER_ROLE"]
    expectation: Literal["ALLOW", "DENY"]
    protected_effects: tuple[MCPProtectedEffectInput, ...] = Field(
        default=(),
        max_length=16,
    )

    def to_domain(self) -> PermissionIntentSemantic:
        return PermissionIntentSemantic(
            effective_state=PermissionIntentEffectiveState(self.effective_state),
            subject_display_name=self.subject_display_name,
            action_display_name=self.action_display_name,
            resource_owner_display_name=self.resource_owner_display_name,
            relation=PermissionIntentRelation(self.relation),
            expectation=PermissionExpectation(self.expectation),
            protected_effects=tuple(item.to_domain() for item in self.protected_effects),
        )


class MCPRepairContractReferenceInput(BaseModel):
    """Agent 只能回传服务端签发的修复来源身份与指纹。"""

    model_config = ConfigDict(extra="forbid")

    source_run_id: str = Field(pattern=r"^run_[0-9a-f]{32}$")
    source_finding_id: str = Field(pattern=r"^finding_[0-9a-f]{32}$")
    repair_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    def to_domain(self) -> RepairContractReference:
        return RepairContractReference.model_validate(self.model_dump(), strict=True)


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
    """每个工具调用都重新校验令牌和当前授权，保证撤销立即生效。"""

    headers: Mapping[str, str] = ctx.headers or {}
    try:
        access.require(
            headers.get("authorization"),
            required_level,
            project_id=project_id,
        )
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
    """MCP 只暴露候选状态，不回传源码位置、内容或指纹。"""

    payload = value.model_dump(mode="json")
    for field in ("source_root", "source_fingerprint", "endpoint_source_fingerprint"):
        payload.pop(field, None)
    for field in ("role_candidates", "action_candidates"):
        for candidate in payload.get(field, []):
            candidate.pop("evidence", None)
    return payload


def _identity_preparation_view(value: BaseModel) -> dict[str, Any]:
    """准备状态不携带内部完整日志路径。"""

    return value.model_dump(mode="json", exclude={"log_path"})


def _recording_view(value: Any) -> dict[str, Any]:
    """Recording 仅保留生命周期摘要，浏览器事件和请求内容永不外发。"""

    payload = _json(value)
    return {
        field: payload[field]
        for field in (
            "recording_id",
            "project_id",
            "flow_id",
            "state",
            "created_at_us",
            "updated_at_us",
            "started_at_us",
            "capture_finished_at_us",
            "finished_at_us",
            "pending_terminal_state",
            "reason_codes",
        )
        if field in payload
    }


def _flow_list_view(values: tuple[dict[str, object], ...]) -> list[dict[str, Any]]:
    """列表只组合 Recording 与 Job 身份/状态，不复制事件或内部错误正文。"""

    summaries: list[dict[str, Any]] = []
    for value in values:
        summary = _recording_view(value)
        job = value.get("job")
        if isinstance(job, dict):
            summary["job"] = {
                field: job[field]
                for field in ("job_id", "run_id", "recording_id", "state")
                if field in job
            }
        else:
            summary["job"] = None
        summaries.append(summary)
    return summaries


def _recording_status_view(value: Any) -> dict[str, Any]:
    """业务流状态不携带浏览器事件或可能含请求模板的 FlowDraft。"""

    return {
        "recording": _recording_view(value.recording),
        "capture_phase": value.capture_phase,
        "draft_available": value.draft is not None,
    }


class MCPBearerGuard:
    """在 SDK 解析协议正文前只接受当前进程签发的 Authorization Bearer。"""

    def __init__(self, app: ASGIApp, access: MCPAccessController) -> None:
        self._app = app
        self._access = access

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        try:
            self._access.authorize(headers.get("authorization"))
        except JiejianError as exc:
            payload = exc.to_dict()
            payload["recovery"] = _recovery_for(exc.code)
            response_headers = (
                {"WWW-Authenticate": "Bearer"}
                if exc.code == ErrorCode.MCP_AUTH_REQUIRED.value
                else None
            )
            response = JSONResponse(
                status_code=(
                    401
                    if exc.code == ErrorCode.MCP_AUTH_REQUIRED.value
                    else 403
                ),
                content={"schema_version": "1", "error": payload},
                headers=response_headers,
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)


class MCPPathAdapter:
    """把 FastAPI 的精确 /mcp 路由适配为 SDK 子应用内部的根路径。"""

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


def build_mcp_control(
    context: ApplicationCore,
    workers: LocalWorkerSupervisor,
    access: MCPAccessController,
    *,
    control_origin: str,
    control_host: str,
) -> MCPControl:
    """注册冻结白名单，并把 SDK ASGI 子应用绑定到当前本地控制 origin。"""

    async def record_client_activity(
        request: ServerRequestContext[Any, Any],
        call_next: Callable[[ServerRequestContext[Any, Any]], Any],
    ) -> HandlerResult:
        result = await call_next(request)
        # initialize 成功后的下一条 SDK 消息会携带已经验证的 client_params。
        params = request.session.client_params
        if params is not None:
            access.note_activity(
                params.client_info.name,
                params.client_info.version,
            )
        return result

    server = MCPServer(
        "界鉴 JIEJIAN",
        description="界鉴本地 Web 产品控制入口；结论仍由确定性 Verification 形成。",
        version=__version__,
        middleware=[record_client_activity],
    )

    @server.tool(name="jiejian_product_status", structured_output=True)
    def product_status(ctx: Context, project_id: str | None = None) -> dict[str, Any]:
        """读取 GUI、CLI 与 MCP 共用的产品状态。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.product_status.get(project_id)))

    @server.tool(name="jiejian_project_list", structured_output=True)
    def project_list(ctx: Context, include_archived: bool = False) -> list[dict[str, Any]]:
        """列出已有 Project，不创建或移除目录。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ)
        return _json(_invoke(lambda: context.projects.list(include_archived=include_archived)))

    @server.tool(name="jiejian_project_show", structured_output=True)
    def project_show(ctx: Context, project_id: str) -> dict[str, Any]:
        """读取一个 Project 的公共记录。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.projects.get(project_id)))

    @server.tool(name="jiejian_application_understanding", structured_output=True)
    def application_understanding(ctx: Context, project_id: str) -> dict[str, Any]:
        """读取去除源码目录的应用理解与候选状态。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        value = _invoke(lambda: context.application_understanding.get(project_id))
        return _understanding_view(value)

    @server.tool(name="jiejian_intent_list", structured_output=True)
    def intent_list(ctx: Context, project_id: str) -> dict[str, Any]:
        """读取人类批准的权限矩阵与实现映射状态。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.permission_intents.matrix(project_id)))

    @server.tool(name="jiejian_intent_show", structured_output=True)
    def intent_show(ctx: Context, project_id: str, intent_id: str) -> dict[str, Any]:
        """读取单一权限意图的不可变 revision 历史。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(
            _invoke(lambda: context.permission_intents.history(project_id, intent_id))
        )

    @server.tool(name="jiejian_identity_list", structured_output=True)
    def identity_list(ctx: Context, project_id: str) -> list[dict[str, Any]]:
        """列出不含秘密引用的测试身份。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.test_identities.list(project_id)))

    @server.tool(name="jiejian_identity_status", structured_output=True)
    def identity_status(ctx: Context, project_id: str, identity_id: str) -> dict[str, Any]:
        """读取一个测试身份的非秘密状态。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        value = _invoke(lambda: context.test_identities.get(identity_id))
        if value.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.PROJECT_NOT_FOUND, "测试身份不属于当前应用"))
        return _json(value)

    @server.tool(name="jiejian_identity_preparation_status", structured_output=True)
    def identity_preparation_status(
        ctx: Context,
        project_id: str,
        preparation_id: str,
    ) -> dict[str, Any]:
        """读取身份准备状态，不返回完整日志路径。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        value = _invoke(lambda: context.identity_preparations.status(preparation_id))
        identity = _invoke(lambda: context.test_identities.get(value.identity_id))
        if identity.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.PROJECT_NOT_FOUND, "身份准备不属于当前应用"))
        return _identity_preparation_view(value)

    @server.tool(name="jiejian_flow_list", structured_output=True)
    def flow_list(ctx: Context, project_id: str) -> list[dict[str, Any]]:
        """列出业务流生命周期摘要，不返回请求正文。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _flow_list_view(
            _invoke(lambda: context.product_flows.list(project_id))
        )

    @server.tool(name="jiejian_flow_status", structured_output=True)
    def flow_status(ctx: Context, project_id: str, recording_id: str) -> dict[str, Any]:
        """读取业务流状态，不返回 FlowDraft 正文。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        value = _invoke(lambda: context.recording_lifecycle.status(recording_id))
        if value.recording.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.PROJECT_NOT_FOUND, "业务流不属于当前应用"))
        return _recording_status_view(value)

    @server.tool(name="jiejian_check_preview", structured_output=True)
    def check_preview(ctx: Context, project_id: str) -> dict[str, Any]:
        """读取开始检查前的范围、缺口和差分覆盖预览。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.checks.preview(project_id)))

    @server.tool(name="jiejian_result_presentation", structured_output=True)
    def result_presentation(ctx: Context, run_id: str) -> dict[str, Any]:
        """读取 GUI、CLI 与 MCP 共用的确定性结果表达。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ)
        return _json(_invoke(lambda: context.result_presentation.build(run_id)))

    @server.tool(name="jiejian_repair_contract_get", structured_output=True)
    def repair_contract_get(
        ctx: Context,
        project_id: str,
        source_run_id: str,
        source_finding_id: str,
    ) -> dict[str, Any]:
        """只读重建已发布 BLOCK 的权威修复要求，不提供补丁或审批能力。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        contract = _invoke(
            lambda: context.repair_contracts.get(source_run_id, source_finding_id)
        )
        if contract.project_id != project_id:
            raise _as_mcp_error(
                JiejianError(ErrorCode.PROJECT_NOT_FOUND, "修复要求不属于当前应用")
            )
        return _json(contract)

    @server.tool(name="jiejian_evidence_index", structured_output=True)
    def evidence_index(ctx: Context, run_id: str) -> list[dict[str, Any]]:
        """读取发布证据索引，不返回完整 Evidence 文档。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ)
        return _json(_invoke(lambda: context.results.read(run_id).evidence))

    @server.tool(name="jiejian_result_history", structured_output=True)
    def result_history(ctx: Context, project_id: str) -> dict[str, Any]:
        """读取同一 Project 的可信结果变化。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        return _json(_invoke(lambda: context.result_history.build(project_id)))

    @server.tool(name="jiejian_system_status", structured_output=True)
    def system_status(ctx: Context) -> dict[str, Any]:
        """读取不含环境变量和路径的本地运行摘要。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ)
        environment = runtime_environment_details()
        return {
            "schema_version": "1",
            "version": __version__,
            "api": "available",
            "worker": "running" if workers.is_running() else "stopped",
            "browser": environment["playwright"]["status"],
            "recovered_jobs": workers.recovered_jobs,
        }

    @server.tool(name="jiejian_intent_propose", structured_output=True)
    def intent_propose(
        ctx: Context,
        project_id: str,
        semantic: MCPPermissionIntentSemanticInput,
        reason: str,
        intent_id: str | None = None,
    ) -> dict[str, Any]:
        """创建待 Human GUI 审阅的语义建议，不修改 revision、hash 或 epoch。"""

        require_mcp_level(access, ctx, MCPAccessLevel.PREPARE, project_id=project_id)
        return _json(
            _invoke(
                lambda: context.permission_intents.propose_semantic_change(
                    project_id,
                    semantic.to_domain(),
                    proposed_by="MCP Agent",
                    reason=reason,
                    intent_id=intent_id,
                )
            )
        )

    @server.tool(name="jiejian_intent_rebind_propose", structured_output=True)
    def intent_rebind_propose(
        ctx: Context,
        project_id: str,
        intent_id: str,
        action_candidate_id: str,
        subject_role_candidate_id: str,
        resource_owner_role_candidate_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """按当前生产事实创建实现重绑建议，不能提交 revision 或改变 epoch。"""

        require_mcp_level(access, ctx, MCPAccessLevel.PREPARE, project_id=project_id)
        return _json(
            _invoke(
                lambda: context.permission_intents.propose_rebind_target(
                    project_id,
                    intent_id,
                    action_candidate_id=action_candidate_id,
                    subject_role_candidate_id=subject_role_candidate_id,
                    resource_owner_role_candidate_id=resource_owner_role_candidate_id,
                    proposed_by="MCP Agent",
                    reason=reason,
                )
            )
        )

    @server.tool(name="jiejian_application_reanalyze", structured_output=True)
    def application_reanalyze(
        ctx: Context,
        project_id: str,
        revision: int,
    ) -> dict[str, Any]:
        """仅在既有源码分析授权仍有效时重新分析已有 Project。"""

        require_mcp_level(access, ctx, MCPAccessLevel.PREPARE, project_id=project_id)
        before = _invoke(lambda: context.application_understanding.get(project_id))
        if not before.source_analysis_authorized:
            raise _as_mcp_error(
                JiejianError(
                    ErrorCode.APPLICATION_ANALYSIS_NOT_AUTHORIZED,
                    "当前应用尚未由用户授权源码只读分析，MCP 不能代为授权。",
                )
            )
        return _understanding_view(
            _invoke(
                lambda: context.application_understanding.analyze_source(
                    project_id,
                    revision=revision,
                )
            )
        )

    @server.tool(name="jiejian_check_prepare", structured_output=True)
    def check_prepare(
        ctx: Context,
        project_id: str,
        change_id: str | None = None,
    ) -> dict[str, Any]:
        """编译已有准备事实；可按服务端变化评估形成重验计划。"""

        require_mcp_level(access, ctx, MCPAccessLevel.PREPARE, project_id=project_id)
        return _json(
            _invoke(lambda: context.checks.prepare(project_id, change_id=change_id))
        )

    @server.tool(name="jiejian_change_submit", structured_output=True)
    def change_submit(
        ctx: Context,
        project_id: str,
        reason: str,
        claimed_paths: tuple[str, ...] = (),
        repair_reference: MCPRepairContractReferenceInput | None = None,
    ) -> dict[str, Any]:
        """声明 Agent 已完成变更；真实文件变化和权限影响由服务端重算。"""

        require_mcp_level(access, ctx, MCPAccessLevel.PREPARE, project_id=project_id)
        manifest, _, _ = _invoke(
            lambda: context.source_changes.submit(
                project_id,
                reason=reason,
                claimed_paths=claimed_paths,
                submitted_by="MCP Agent",
                **(
                    {}
                    if repair_reference is None
                    else {"repair_reference": repair_reference.to_domain()}
                ),
            )
        )
        return _json(_invoke(lambda: context.source_changes.view(manifest.change_id)))

    @server.tool(name="jiejian_change_show", structured_output=True)
    def change_show(
        ctx: Context,
        project_id: str,
        change_id: str,
    ) -> dict[str, Any]:
        """读取代码变化的有界影响摘要，不返回文件清单或源码。"""

        require_mcp_level(access, ctx, MCPAccessLevel.READ, project_id=project_id)
        view = _invoke(lambda: context.source_changes.view(change_id))
        if view.project_id != project_id:
            raise _as_mcp_error(
                JiejianError(ErrorCode.PROJECT_NOT_FOUND, "代码变化不属于当前应用")
            )
        return _json(view)

    @server.tool(name="jiejian_identity_prepare_start", structured_output=True)
    def identity_prepare_start(
        ctx: Context,
        project_id: str,
        identity_id: str,
    ) -> dict[str, Any]:
        """启动既有测试身份的受控登录准备。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        identity = _invoke(lambda: context.test_identities.get(identity_id))
        if identity.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.PROJECT_NOT_FOUND, "测试身份不属于当前应用"))
        return _identity_preparation_view(
            _invoke(lambda: context.identity_preparations.start(identity_id))
        )

    @server.tool(name="jiejian_identity_prepare_confirm", structured_output=True)
    def identity_prepare_confirm(
        ctx: Context,
        project_id: str,
        preparation_id: str,
    ) -> dict[str, Any]:
        """确认受控身份准备进程的保存动作。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        status = _invoke(lambda: context.identity_preparations.status(preparation_id))
        identity = _invoke(lambda: context.test_identities.get(status.identity_id))
        if identity.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.PROJECT_NOT_FOUND, "身份准备不属于当前应用"))
        return _identity_preparation_view(
            _invoke(lambda: context.identity_preparations.confirm(preparation_id))
        )

    @server.tool(name="jiejian_identity_prepare_cancel", structured_output=True)
    def identity_prepare_cancel(
        ctx: Context,
        project_id: str,
        preparation_id: str,
    ) -> dict[str, Any]:
        """取消受控身份准备进程。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        status = _invoke(lambda: context.identity_preparations.status(preparation_id))
        identity = _invoke(lambda: context.test_identities.get(status.identity_id))
        if identity.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.PROJECT_NOT_FOUND, "身份准备不属于当前应用"))
        return _identity_preparation_view(
            _invoke(lambda: context.identity_preparations.cancel(preparation_id))
        )

    @server.tool(name="jiejian_recording_start", structured_output=True)
    def recording_start(
        ctx: Context,
        project_id: str,
        action_candidate_id: str,
        test_identity_id: str,
        duration_seconds: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """启动已有动作和测试身份的受控 Recording。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        started = _invoke(
            lambda: context.project_recordings.submit(
                project_id,
                action_candidate_id=action_candidate_id,
                test_identity_id=test_identity_id,
                duration_seconds=duration_seconds,
                idempotency_key=idempotency_key,
                headless=False,
            )
        )
        return {
            "job": _json(started.result.job),
            "recording": _json(started.result.recording),
            "action_candidate_id": started.action.candidate_id,
            "test_identity_id": started.test_identity.identity_id,
        }

    @server.tool(name="jiejian_recording_capture_start", structured_output=True)
    def recording_capture_start(
        ctx: Context,
        project_id: str,
        recording_id: str,
    ) -> dict[str, Any]:
        """在浏览器准备完成后开始采集当前 Recording。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        before = _invoke(lambda: context.recording_lifecycle.status(recording_id))
        if before.recording.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.PROJECT_NOT_FOUND, "业务流不属于当前应用"))
        return _recording_status_view(
            _invoke(lambda: context.recording_lifecycle.start_capture(recording_id))
        )

    @server.tool(name="jiejian_recording_stop", structured_output=True)
    def recording_stop(
        ctx: Context,
        project_id: str,
        recording_id: str,
    ) -> dict[str, Any]:
        """停止当前 Recording 采集并保留已形成的事件。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        before = _invoke(lambda: context.recording_lifecycle.status(recording_id))
        if before.recording.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.PROJECT_NOT_FOUND, "业务流不属于当前应用"))
        return _recording_status_view(
            _invoke(lambda: context.recording_lifecycle.stop_capture(recording_id))
        )

    @server.tool(name="jiejian_check_run", structured_output=True)
    def check_run(
        ctx: Context,
        project_id: str,
        idempotency_key: str,
        change_id: str | None = None,
    ) -> dict[str, Any]:
        """提交当前已准备的检查，不允许指定任意 Profile。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        result, request, _ = _invoke(
            lambda: context.checks.submit(
                project_id,
                idempotency_key=idempotency_key,
                change_id=change_id,
            )
        )
        return {
            "schema_version": request.schema_version,
            "job": _json(result.job),
            "run": _json(result.run),
        }

    @server.tool(name="jiejian_check_cancel", structured_output=True)
    def check_cancel(
        ctx: Context,
        project_id: str,
        job_id: str,
    ) -> dict[str, Any]:
        """取消属于当前 Project 的检查 Job。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        with context.uow_factory() as work:
            job = work.jobs.get(job_id)
            run = work.runs.get(job.run_id) if job is not None and job.run_id else None
        if job is None or run is None or run.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.JOB_NOT_FOUND, "当前应用中不存在该检查任务"))
        return _json(
            _invoke(
                lambda: context.job_queue.request_cancellation(
                    RequestCancellation(
                        job_id=job_id,
                        now_us=time.time_ns() // 1_000,
                    )
                )
            )
        )

    @server.tool(name="jiejian_official_sample_start", structured_output=True)
    def official_sample_start(
        ctx: Context,
        project_id: str,
        experience_mode: Literal["GUIDED", "FULL"],
        consent: Literal[True],
    ) -> dict[str, Any]:
        """为已存在且已授权的官方 Sample Project 启动正式体验。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        _invoke(lambda: context.projects.get(project_id))
        started = _invoke(
            lambda: context.official_experience.start(
                OfficialExperienceMode(experience_mode),
                consent=consent,
            )
        )
        if started.project_id != project_id:
            context.official_experience.stop()
            raise _as_mcp_error(
                JiejianError(
                    ErrorCode.OFFICIAL_SAMPLE_CONFLICT,
                    "启动后的官方示例不属于已授权 Project，已安全停止。",
                )
            )
        return _json(started)

    @server.tool(name="jiejian_official_sample_stop", structured_output=True)
    def official_sample_stop(ctx: Context, project_id: str) -> dict[str, Any]:
        """停止属于当前已授权 Project 的官方 Sample。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        status = _invoke(context.official_experience.status)
        if status.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.OFFICIAL_SAMPLE_CONFLICT, "官方示例不属于当前应用"))
        return _json(_invoke(context.official_experience.stop))

    @server.tool(name="jiejian_official_sample_verify_fixed", structured_output=True)
    def official_sample_verify_fixed(
        ctx: Context,
        project_id: str,
        verification_run_id: str,
    ) -> dict[str, Any]:
        """按既有官方体验合同切换到修复后行为，不代替后续检查。"""

        require_mcp_level(access, ctx, MCPAccessLevel.EXECUTE, project_id=project_id)
        status = _invoke(context.official_experience.status)
        if status.project_id != project_id:
            raise _as_mcp_error(JiejianError(ErrorCode.OFFICIAL_SAMPLE_CONFLICT, "官方示例不属于当前应用"))
        return _json(
            _invoke(
                lambda: context.official_experience.switch_behavior(
                    authorization_order="AUTHORIZE_BEFORE_ENQUEUE",
                    blob_observation="AVAILABLE",
                    verification_run_id=verification_run_id,
                )
            )
        )

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
    return MCPControl(
        server=server,
        app=MCPPathAdapter(MCPBearerGuard(sdk_app, access)),
    )


__all__ = [
    "MCPBearerGuard",
    "MCPControl",
    "MCPPathAdapter",
    "MCPPermissionIntentSemanticInput",
    "MCPProtectedEffectInput",
    "MCPRepairContractReferenceInput",
    "build_mcp_control",
    "require_mcp_level",
]
