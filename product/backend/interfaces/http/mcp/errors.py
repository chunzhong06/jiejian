# 统一 MCP 授权检查和错误净化；验证异常不回显候选原文或秘密。
from __future__ import annotations
from collections.abc import Callable, Mapping
from typing import TypeVar
import logging
import re
from uuid import uuid4
from product.backend import __version__
from mcp import MCPError
from mcp.server.mcpserver import Context
from pydantic import BaseModel, ValidationError
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.application.agent_access.service import MCPAccessController, MCPAccessLevel

_T = TypeVar("_T")

_ACCESS_ERROR_CODES = {
    ErrorCode.MCP_DISABLED.value: -32041,
    ErrorCode.MCP_AUTH_REQUIRED.value: -32042,
    ErrorCode.MCP_PERMISSION_REQUIRED.value: -32043,
}

def _recovery_for(code: str) -> str:
    return {
        ErrorCode.MCP_DISABLED.value: "请在界鉴的“AI 工具连接”面板中启用连接后重试。",
        ErrorCode.MCP_AUTH_REQUIRED.value: "请在界鉴的连接与授权页核对连接是否暂停或失效，并按所选客户端指引恢复；无需复制凭据。",
        ErrorCode.MCP_PERMISSION_REQUIRED.value: "请打开界鉴“连接与授权”，选择本应用并调整允许范围。所需级别见 required_level；保存候选和建议需要 PREPARE。不得代替用户授权。",
        ErrorCode.INPUT_INVALID.value: "读取当前工具上下文，按字段提示修正输入；不改变原业务要求或绕过人工批准。",
        ErrorCode.STORAGE_STATE.value: "界鉴内部记录未能读取。保留业务要求与材料，提供诊断编号，并在界鉴系统状态页核对实际版本与前端构建；不要通过改权限或删除候选重试。",
    }.get(code, "请回到界鉴查看当前应用状态并按页面提示恢复。")

def _as_mcp_error(exc: JiejianError) -> MCPError:
    payload = exc.to_dict()
    details = payload.get("details", {})
    recovery = _recovery_for(exc.code)
    if details.get("reason") in {"CANDIDATE_QUESTION_REVIEW_REQUIRED", "CANDIDATE_SCENARIO_REVIEW_REQUIRED", "CANDIDATE_SELECTED_REQUIREMENT_CHANGED"}:
        recovery = details["recovery"]
    return MCPError(
        code=_ACCESS_ERROR_CODES.get(exc.code, -32010),
        message=str(payload["message"]),
        data={
            "error_code": exc.code,
            "details": details,
            "recovery": recovery,
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

def _validation_issues(exc: ValidationError, model: type[BaseModel], root: str = 'candidate') -> list[dict]:
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
        'requirement_permission_outside': 'permission_item_ids只能引用本候选content.permissions中存在的item_id；请补齐实际权限或纠正关联，不能删除原始要求',
        'coverage_permission_outside': 'targets中的permission_item_id必须引用本候选实际权限项',

        "disclosure_projection_required": "DATA_DISCLOSURE必须填写非空的protected_projection，字段须对应真实业务数据",
        "projection_not_applicable": "只有DATA_DISCLOSURE可以填写protected_projection，其他类型应留空",
        "projection_invalid": "字段清单不得重复，字段名须以英文字母开头且只包含字母、数字、下划线、点或连字符",
        "scenario_excerpt_mismatch": "original_excerpt须来自original_text原话，occurrence不得超过该摘录实际出现次数；不要为匹配摘录改写原始要求",
        "scenario_replacement_outside": "replacements.item_id必须复用当前content.permissions中的权限项标识",
        "scenario_replacement_set_mismatch": "同一情境的每个选项必须替换同一组权限项标识",
        "scenario_replacement_duplicate": "一个选项不能重复替换同一权限项；不同选项可以引用同一权限项",
        "scenario_option_duplicate": "同一情境内option_id不能重复",
        "scenario_id_duplicate": "同一候选内scenario_id不能重复",
        "missing": "缺少必填字段", "extra_forbidden": "包含未声明字段，请对照当前输入格式删除",
        "enum": "值不在允许的枚举中", "string_pattern_mismatch": "字段格式不符合公开约束，请按当前 input_schema 中该路径的 pattern 填写；operation_id 为32位小写十六进制，不含连字符",
        "too_short": "条目数量不足", "too_long": "条目数量超过上限",
        "string_type": "需要文本", "bool_type": "需要布尔值", "int_type": "需要整数",
    }
    errors = exc.errors(include_input=False, include_context=True, include_url=False)
    issues = []
    for error in errors:
        location = error["loc"]
        # 子项被拒引起的列表长度错误不重复展示，避免误导Agent添加无意义条目。
        if error["type"] == "too_short" and any(len(e["loc"]) > len(location) and e["loc"][:len(location)] == location for e in errors):
            continue
        path = root
        for part in location[:16]:
            path += f"[{part}]" if type(part) is int and 0 <= part < 10000 else "." + (part if isinstance(part, str) and part in allowed else "<field>")
        code = error["type"] if error["type"] in explanations else "invalid_value"
        if code in {'requirement_permission_outside','coverage_permission_outside'}:
            index = error.get('ctx', {}).get('source_index')
            path += '.requirement_sources' if code == 'requirement_permission_outside' else '.coverage_suggestions'
            if type(index) is int and 0 <= index < 100:
                path += f'[{index}]'
            path += '.permission_item_ids' if code == 'requirement_permission_outside' else '.targets'
        elif code in {"disclosure_projection_required", "projection_not_applicable"}:
            path += ".protected_projection"
        elif code in {"scenario_excerpt_mismatch", "scenario_replacement_outside"}:
            # 只消费自有校验器产生的两个整数索引，不回显任意ctx或异常对象。
            context = error.get("ctx", {})
            scenario_index = context.get("scenario_index")
            path += ".scenarios"
            if type(scenario_index) is int and 0 <= scenario_index < 10:
                path += f"[{scenario_index}]"
            if code == "scenario_excerpt_mismatch":
                path += ".original_excerpt"
            else:
                option_index = context.get("option_index")
                path += ".options"
                if type(option_index) is int and 0 <= option_index < 4:
                    path += f"[{option_index}]"
                path += ".replacements"
        elif code == "scenario_id_duplicate":
            path += ".scenarios"
        elif code in {"scenario_option_duplicate", "scenario_replacement_set_mismatch"}:
            path += ".options"
        elif code == "scenario_replacement_duplicate":
            path += ".replacements"
        issues.append({"path": path, "code": code, "message": explanations.get(code, "值不符合当前输入格式或字段组合约束")})
        if len(issues) == 8:
            break
    return issues


def _invoke(operation: Callable[[], _T], *, input_model: type[BaseModel] | None = None, input_root: str = 'candidate', diagnostic_context: dict | None = None) -> _T:
    try:
        return operation()
    except JiejianError as exc:
        raise _as_mcp_error(exc) from None
    except ValidationError as exc:
        # 候选中的原文和技术输入不进入SDK异常正文或日志。
        if input_model is not None:
            issues = _validation_issues(exc, input_model, input_root)
            summary = "；".join(f"{item['path']}：{item['message']}" for item in issues[:3])
            raise _as_mcp_error(JiejianError(ErrorCode.INPUT_INVALID, "工具输入不符合公开合同：" + summary,
                details={"issues": issues, "recovery": "读取当前工具上下文，按字段提示修正输入；不要修改业务含义来绕过校验"})) from None
        diagnostic_id = uuid4().hex
        # 只记录受控标识与错误数量，不记录异常正文、原文、秘密或客户端任意字段。
        safe = {key:value for key,value in (diagnostic_context or {}).items()
            if key in {'project_id', 'candidate_id', 'tool', 'revision'} and
            (type(value) is int and value >= 0 or isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_]{1,96}', value))}
        details = {'diagnostic_id':diagnostic_id, 'version':__version__, 'validation_error_count':exc.error_count(), **safe}
        logging.getLogger(__name__).error('MCP internal record validation: %s', details)
        raise _as_mcp_error(JiejianError(ErrorCode.STORAGE_STATE,
            '界鉴内部记录校验失败，尚未完成本次读取；请保留现有业务要求并提交诊断编号', details=details)) from None
