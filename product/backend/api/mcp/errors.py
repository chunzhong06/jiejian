# 统一 MCP 授权检查和错误净化；验证异常不回显候选原文或秘密。
from __future__ import annotations
from collections.abc import Callable, Mapping
from typing import TypeVar
from mcp import MCPError
from mcp.server.mcpserver import Context
from pydantic import BaseModel, ValidationError
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.agent_access.service import MCPAccessController, MCPAccessLevel

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
        ErrorCode.INPUT_INVALID.value: "读取当前工具上下文，按字段提示修正输入；不改变原业务要求或绕过人工批准。",
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

def _validation_issues(exc: ValidationError, model: type[BaseModel]) -> list[dict]:
    """只返回Schema声明的字段名、有限索引与固定说明；动态键和异常正文均不透出。"""
    allowed: set[str] = set()

    def collect(node):
        if isinstance(node, dict):
            allowed.update(node.get("properties", {}))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(model.model_json_schema())
    explanations = {
        "disclosure_projection_required": "DATA_DISCLOSURE必须填写非空的protected_projection，字段须对应真实业务数据",
        "projection_not_applicable": "只有DATA_DISCLOSURE可以填写protected_projection，其他类型应留空",
        "projection_invalid": "字段清单不得重复，字段名须以英文字母开头且只包含字母、数字、下划线、点或连字符",
        "missing": "缺少必填字段", "extra_forbidden": "包含未声明字段，请对照当前输入格式删除",
        "enum": "值不在允许的枚举中", "string_pattern_mismatch": "字段格式不符合公开约束",
        "too_short": "条目数量不足", "too_long": "条目数量超过上限",
        "string_type": "需要文本", "bool_type": "需要布尔值", "int_type": "需要整数",
    }
    errors = exc.errors(include_input=False, include_context=False, include_url=False)
    issues = []
    for error in errors:
        location = error["loc"]
        # 子项被拒引起的列表长度错误不重复展示，避免误导Agent添加无意义条目。
        if error["type"] == "too_short" and any(len(e["loc"]) > len(location) and e["loc"][:len(location)] == location for e in errors):
            continue
        path = "candidate"
        for part in location[:16]:
            path += f"[{part}]" if type(part) is int and 0 <= part < 10000 else "." + (part if isinstance(part, str) and part in allowed else "<field>")
        code = error["type"] if error["type"] in explanations else "invalid_value"
        if code in {"disclosure_projection_required", "projection_not_applicable"}:
            path += ".protected_projection"
        issues.append({"path": path, "code": code, "message": explanations.get(code, "值不符合当前输入格式或字段组合约束")})
        if len(issues) == 8:
            break
    return issues


def _invoke(operation: Callable[[], _T], *, input_model: type[BaseModel] | None = None) -> _T:
    try:
        return operation()
    except JiejianError as exc:
        raise _as_mcp_error(exc) from None
    except ValidationError as exc:
        # 候选中的原文和技术输入不进入SDK异常正文或日志。
        if input_model is not None:
            issues = _validation_issues(exc, input_model)
            summary = "；".join(f"{item['path']}：{item['message']}" for item in issues[:3])
            raise _as_mcp_error(JiejianError(ErrorCode.INPUT_INVALID, "工具输入不符合公开合同：" + summary,
                details={"issues": issues, "recovery": "读取当前规则上下文，按字段提示修正候选后重新提交；不要修改业务含义来绕过校验"})) from None
        raise _as_mcp_error(JiejianError(ErrorCode.INPUT_INVALID, "工具输入不符合公开合同，请读取上下文中的输入格式")) from None
