# =============================================================================
# Verification 输入加载
#
# 定位
#   磁盘 ProjectBundle、Flow 和 YAML Contract 进入领域模型的受限边界
#
# 职责
#   严格 YAML 解析｜根目录内引用解析｜跨文件 ID 和语义校验
#
# 调用链
#   Projects / CLI → load_project_bundle / load_flow / load_contract → verification.models
# =============================================================================

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ValidationError

from ..domain.lifecycle import ContractStatus
from .models import (
    Flow,
    ProjectDefinition,
    RuleKind,
    SecurityContract,
)
from ..errors import ErrorCode, JiejianError

ModelT = TypeVar("ModelT", bound=BaseModel)
_MAX_YAML_BYTES = 1_048_576


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """安全 Loader，同时拒绝会掩盖配置的重复键。"""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True, slots=True)
class ProjectBundle:
    project_file: Path
    project: ProjectDefinition
    flow: Flow
    contract: SecurityContract


def load_project_bundle(
    project_path: Path,
    *,
    contract_path: Path | None = None,
) -> ProjectBundle:
    project_file = project_path.resolve()
    document = _load_yaml(project_file)
    unexpected = set(document).difference(
        {
            "schema_version",
            "project",
            "target",
            "identities",
            "resources",
            "flow",
            "contract",
            "observers",
            "mutation_seed",
        }
    )
    if unexpected:
        raise JiejianError(
            ErrorCode.INPUT_INVALID,
            "项目文件包含未知字段",
            details={"fields": sorted(unexpected)},
        )
    project_section = document.get("project")
    if not isinstance(project_section, dict):
        raise JiejianError(ErrorCode.INPUT_INVALID, "项目文件缺少 project 表")
    if set(project_section).difference({"id", "name"}):
        raise JiejianError(ErrorCode.INPUT_INVALID, "project 表包含未知字段")
    observers = document.get("observers", {})
    if not isinstance(observers, dict) or set(observers).difference({"owner_api"}):
        raise JiejianError(ErrorCode.INPUT_INVALID, "observers 表结构无效")

    root = project_file.parent
    flow_file = _resolve_reference(root, document.get("flow"), "flow")
    default_contract = _resolve_reference(root, document.get("contract"), "contract")
    selected_contract = contract_path.resolve() if contract_path else default_contract
    if not selected_contract.is_file():
        raise JiejianError(ErrorCode.INPUT_FILE, "契约文件不存在")
    project = _validate_model(
        ProjectDefinition,
        {
            "schema_version": document.get("schema_version"),
            "id": project_section.get("id"),
            "name": project_section.get("name"),
            "target": document.get("target"),
            "identities": document.get("identities"),
            "resources": document.get("resources"),
            "flow_path": flow_file,
            "contract_path": selected_contract,
            "owner_observer_enabled": observers.get("owner_api", True),
            "mutation_seed": document.get("mutation_seed", 7),
        },
        "项目",
    )
    flow = load_flow(flow_file)
    contract = load_contract(selected_contract)
    _validate_bundle(project, flow, contract)
    return ProjectBundle(
        project_file=project_file,
        project=project,
        flow=flow,
        contract=contract,
    )


def load_flow(path: Path) -> Flow:
    document = _load_yaml(path)
    section = document.get("flow")
    if not isinstance(section, dict):
        raise JiejianError(ErrorCode.INPUT_INVALID, "Flow 文件缺少 flow 表")
    return _validate_model(
        Flow,
        {"schema_version": document.get("schema_version"), **section},
        "Flow",
    )


def load_contract(path: Path) -> SecurityContract:
    document = _load_yaml(path)
    section = document.get("contract")
    if not isinstance(section, dict):
        raise JiejianError(ErrorCode.INPUT_INVALID, "契约文件缺少 contract 表")
    return _validate_model(
        SecurityContract,
        {"schema_version": document.get("schema_version"), **section},
        "契约",
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw_bytes = path.read_bytes()
        if len(raw_bytes) > _MAX_YAML_BYTES:
            raise JiejianError(ErrorCode.INPUT_FILE, "YAML 文件超过 1 MiB 限制")
        raw = raw_bytes.decode("utf-8")
        if any(
            isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
            for token in yaml.scan(raw)
        ):
            raise JiejianError(ErrorCode.INPUT_FILE, "YAML 不允许锚点或别名")
        document = yaml.load(raw, Loader=_UniqueKeySafeLoader)
    except JiejianError:
        raise
    except UnicodeDecodeError as exc:
        raise JiejianError(ErrorCode.INPUT_FILE, "YAML 文件必须使用 UTF-8") from exc
    except (OSError, yaml.YAMLError) as exc:
        raise JiejianError(
            ErrorCode.INPUT_FILE,
            "无法安全读取 YAML 文件",
            details={"reason": type(exc).__name__},
        ) from exc
    if not isinstance(document, dict) or document.get("schema_version") != "1":
        raise JiejianError(
            ErrorCode.INPUT_INVALID,
            "YAML 必须是带 schema_version=1 的对象",
        )
    return document


def _resolve_reference(root: Path, raw: Any, label: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise JiejianError(ErrorCode.INPUT_INVALID, f"项目文件缺少 {label} 引用")
    reference = Path(raw)
    if reference.is_absolute():
        raise JiejianError(ErrorCode.INPUT_PATH, f"{label} 引用必须是相对路径")
    resolved = (root / reference).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise JiejianError(ErrorCode.INPUT_PATH, f"{label} 引用越出项目目录")
    if not resolved.is_file():
        raise JiejianError(ErrorCode.INPUT_FILE, f"{label} 引用文件不存在")
    return resolved


def _validate_model(
    model: type[ModelT],
    data: Mapping[str, Any],
    label: str,
) -> ModelT:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        issues = [
            {
                "location": ".".join(str(part) for part in issue["loc"]),
                "type": issue["type"],
            }
            for issue in exc.errors()
        ]
        raise JiejianError(
            ErrorCode.INPUT_INVALID,
            f"{label}校验失败",
            details={"issues": issues},
        ) from exc


def _validate_bundle(
    project: ProjectDefinition,
    flow: Flow,
    contract: SecurityContract,
) -> None:
    identity_ids = {identity.id for identity in project.identities}
    resource_ids = {resource.id for resource in project.resources}
    step_ids = {step.id for step in flow.steps}
    rule_ids = {rule.id for rule in contract.rules}
    rule_kinds = {rule.kind for rule in contract.rules}
    if len(identity_ids) != len(project.identities):
        raise JiejianError(ErrorCode.INPUT_INVALID, "身份 ID 不得重复")
    if len(resource_ids) != len(project.resources):
        raise JiejianError(ErrorCode.INPUT_INVALID, "资源 ID 不得重复")
    if len(step_ids) != len(flow.steps):
        raise JiejianError(ErrorCode.INPUT_INVALID, "Flow 步骤 ID 不得重复")
    if len(rule_ids) != len(contract.rules) or len(rule_kinds) != len(contract.rules):
        raise JiejianError(ErrorCode.INPUT_INVALID, "契约规则 ID 和 kind 不得重复")
    if any(
        resource.owner_identity_id not in identity_ids
        for resource in project.resources
    ):
        raise JiejianError(ErrorCode.INPUT_INVALID, "资源所有者身份不存在")
    if any(
        reference not in identity_ids
        for step in flow.steps
        for reference in (step.identity_id, step.alternate_identity_id)
    ):
        raise JiejianError(ErrorCode.INPUT_INVALID, "Flow 身份引用不存在")
    if any(
        reference not in resource_ids
        for step in flow.steps
        for reference in (step.resource_id, step.alternate_resource_id)
    ):
        raise JiejianError(ErrorCode.INPUT_INVALID, "Flow 资源引用不存在")
    if contract.status is not ContractStatus.ACTIVE:
        raise JiejianError(ErrorCode.INPUT_INVALID, "阶段 1 运行只接受 ACTIVE 契约")
    required_kinds = {RuleKind.FOREIGN_READ}
    if any(step.method != "GET" for step in flow.steps):
        required_kinds.update(
            {RuleKind.UNAUTHORIZED_SIDE_EFFECT, RuleKind.PRIVILEGED_FIELD}
        )
    if not required_kinds.issubset(rule_kinds):
        raise JiejianError(ErrorCode.INPUT_INVALID, "契约缺少 Flow 所需关系规则")
