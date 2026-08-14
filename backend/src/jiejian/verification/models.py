# =============================================================================
# Verification 领域数据模型
#
# 定位
#   承接已校验的项目输入，并为关系变异、执行、观察和证据提供统一数据结构
#
# 职责
#   约束目标与 Flow｜表达 Contract 规则｜保存 MutationPlan、Observation 和 Evidence
#
# 调用链
#   inputs / runner protocol → verification.models → planning / execution / evaluation
# =============================================================================

from __future__ import annotations

import ipaddress
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from ..domain.identifiers import LONG_SLUG_ID_PATTERN, PROJECT_ID_PATTERN
from ..domain.lifecycle import CaseVerdict, ContractStatus, DomainModel, RunVerdict


# 标识契约要检查的所有权安全关系。
class RuleKind(StrEnum):
    FOREIGN_READ = "foreign_read"
    UNAUTHORIZED_SIDE_EFFECT = "unauthorized_side_effect"
    PRIVILEGED_FIELD = "privileged_field"


# 标识规划器对正常 FlowStep 施加的攻击变化。
class MutationKind(StrEnum):
    IDENTITY_SWAP = "identity_swap"
    RESOURCE_SWAP = "resource_swap"
    PRIVILEGED_FIELD = "privileged_field"


# 统一记录单个测试无法通过或无法下结论的直接原因。
class ReasonCode(StrEnum):
    FOREIGN_RESOURCE_OBSERVED = "FOREIGN_RESOURCE_OBSERVED"
    UNAUTHORIZED_SIDE_EFFECT = "UNAUTHORIZED_SIDE_EFFECT"
    PRIVILEGED_FIELD_ACCEPTED = "PRIVILEGED_FIELD_ACCEPTED"
    REQUIRED_OBSERVER_MISSING = "REQUIRED_OBSERVER_MISSING"
    BASELINE_PRECONDITION_FAILED = "BASELINE_PRECONDITION_FAILED"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    UNEXPECTED_HTTP_RESPONSE = "UNEXPECTED_HTTP_RESPONSE"


# 保存一次验证明确获准访问的目标范围和请求预算。
class TargetScope(DomainModel):
    base_url: str
    allowed_origins: tuple[str, ...]
    allowed_hosts: tuple[str, ...]
    allowed_ports: tuple[int, ...]
    allow_private_network: bool = False
    follow_redirects: Literal[False] = False
    timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    max_requests: int = Field(default=64, ge=1, le=500)
    max_response_bytes: int = Field(default=262_144, ge=1, le=4_194_304)

    @field_validator("allowed_hosts")
    @classmethod
    def normalize_hosts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """去重并规范化显式 IPv4 主机，拒绝阶段 1 尚不能安全固定的域名。"""

        normalized = tuple(dict.fromkeys(value.strip().lower() for value in values))
        if not normalized or any(not value for value in normalized):
            raise ValueError("allowed_hosts must contain explicit hosts")
        try:
            addresses = tuple(str(ipaddress.IPv4Address(value)) for value in normalized)
        except ipaddress.AddressValueError as exc:
            raise ValueError("stage 1 allowed_hosts must be IPv4 literals") from exc
        return addresses

    @field_validator("allowed_ports")
    @classmethod
    def normalize_ports(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        """去重端口并拒绝空列表或超出 TCP/UDP 有效范围的值。"""

        normalized = tuple(dict.fromkeys(values))
        if not normalized or any(port < 1 or port > 65535 for port in normalized):
            raise ValueError("allowed_ports must contain valid explicit ports")
        return normalized

    @model_validator(mode="after")
    def validate_scope(self) -> TargetScope:
        """确认 base_url 完全落在声明的 origin、主机和端口授权范围内。"""

        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("base_url must use HTTP or HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("base_url must not contain user information")
        if parsed.hostname is None:
            raise ValueError("base_url must contain a host")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("base_url must be an origin without path, query, or fragment")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise ValueError("base_url contains an invalid port") from exc
        host = parsed.hostname.lower()
        try:
            host = str(ipaddress.IPv4Address(host))
        except ipaddress.AddressValueError as exc:
            raise ValueError("stage 1 base_url host must be an IPv4 literal") from exc
        if host not in self.allowed_hosts:
            raise ValueError("base_url host is outside allowed_hosts")
        if port not in self.allowed_ports:
            raise ValueError("base_url port is outside allowed_ports")

        origins: list[str] = []
        for raw_origin in self.allowed_origins:
            origin = urlsplit(raw_origin)
            if (
                origin.scheme not in {"http", "https"}
                or origin.hostname is None
                or origin.username is not None
                or origin.password is not None
                or origin.path not in {"", "/"}
                or origin.query
                or origin.fragment
            ):
                raise ValueError("allowed_origins must contain normalized HTTP origins")
            origin_port = origin.port or (443 if origin.scheme == "https" else 80)
            try:
                origin_host = str(ipaddress.IPv4Address(origin.hostname))
            except ipaddress.AddressValueError as exc:
                raise ValueError(
                    "stage 1 allowed_origins must use IPv4 literals"
                ) from exc
            origins.append(f"{origin.scheme}://{origin_host}:{origin_port}")
        normalized_origins = tuple(dict.fromkeys(origins))
        base_origin = f"{parsed.scheme}://{host}:{port}"
        if base_origin not in normalized_origins:
            raise ValueError("base_url origin is outside allowed_origins")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))
        object.__setattr__(self, "allowed_origins", normalized_origins)

        address = ipaddress.IPv4Address(host)
        if not self.allow_private_network and is_restricted_address(address):
            raise ValueError("private or local base_url requires explicit authorization")
        return self


def is_restricted_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    """判断地址是否属于默认拒绝的非公网范围。"""

    return any(
        (
            not address.is_global,
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


# 描述一个测试身份；只保存外部秘密引用，不保存真实凭据。
class Identity(DomainModel):
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    role: str = Field(min_length=1, max_length=64)
    secret_ref: str = Field(pattern=r"^env:[A-Z][A-Z0-9_]{0,127}$")


# 把资源 ID 与其合法所有者身份连接起来，供规划和观察阶段查询。
class ResourceDefinition(DomainModel):
    id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    owner_identity_id: str


# 描述一个 Flow 步骤从已声明依赖步骤中取得动态值的方式。
class FlowVariableSource(DomainModel):
    name: str = Field(pattern=PROJECT_ID_PATTERN)
    source_step_id: str = Field(pattern=PROJECT_ID_PATTERN)
    source_event_sequence: int = Field(ge=1)
    json_path: str = Field(min_length=1, max_length=512)


# 保存正常业务操作和派生攻击测试所需的替代身份、资源。
# inputs.load_flow 构造合法基线，planning.build_mutation_plan 再生成 MutationCase。
class FlowStep(DomainModel):
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    method: Literal["GET", "PATCH", "POST", "PUT", "DELETE"]
    path: str
    identity_id: str
    resource_id: str
    alternate_identity_id: str
    alternate_resource_id: str
    json_body: dict[str, Any] = Field(default_factory=dict)
    expected_statuses: tuple[int, ...] = (200,)
    depends_on_step_ids: tuple[str, ...] = Field(default=(), max_length=128)
    variable_sources: tuple[FlowVariableSource, ...] = Field(default=(), max_length=128)
    sensitive_fields: tuple[str, ...] = Field(default=(), max_length=256)

    @field_validator("path")
    @classmethod
    def validate_relative_http_path(cls, value: str) -> str:
        """只接受当前目标站点内的绝对路径引用，拒绝外部地址和目录跳转。"""

        parsed = urlsplit(value)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or any(segment in {".", ".."} for segment in parsed.path.split("/"))
        ):
            raise ValueError("flow step path must be an absolute-path reference")
        return value

    @field_validator("json_body")
    @classmethod
    def reject_inline_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        """拒绝疑似凭据字段，防止真实秘密随 Flow YAML 进入快照或工件。"""

        if any(
            re.search(
                r"authorization|cookie|credential|password|secret|token|api[_-]?key",
                str(key),
                re.IGNORECASE,
            )
            for key in value
        ):
            raise ValueError("flow JSON must not contain inline credential fields")
        return value

    @model_validator(mode="after")
    def validate_flow_step_metadata(self) -> FlowStep:
        """确保步骤依赖、动态变量名和敏感字段声明各自不重复。"""

        if len(set(self.depends_on_step_ids)) != len(self.depends_on_step_ids):
            raise ValueError("flow step dependencies must be unique")
        variable_names = {source.name for source in self.variable_sources}
        if len(variable_names) != len(self.variable_sources):
            raise ValueError("flow step variable sources must be unique")
        if len(set(self.sensitive_fields)) != len(self.sensitive_fields):
            raise ValueError("flow step sensitive fields must be unique")
        return self


# 按依赖关系保存可重放的正常业务步骤，并声明观察与清理端点。
class Flow(DomainModel):
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    steps: tuple[FlowStep, ...] = Field(min_length=1)
    owner_observer_path: str = "/owner/resources/{resource_id}"
    reset_path: str = "/reset"

    @field_validator("owner_observer_path", "reset_path")
    @classmethod
    def validate_support_path(cls, value: str) -> str:
        """限制观察和清理端点为当前目标内、不带查询参数的绝对路径引用。"""

        parsed = urlsplit(value)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or parsed.query
            or parsed.fragment
            or any(segment in {".", ".."} for segment in parsed.path.split("/"))
        ):
            raise ValueError("support endpoint must be an absolute-path reference")
        return value

    @model_validator(mode="after")
    def validate_dependency_graph(self) -> Flow:
        """验证步骤 ID、依赖引用和变量来源，并拒绝无法按顺序重放的依赖环。"""

        step_ids = tuple(step.id for step in self.steps)
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("flow step IDs must be unique")
        known = set(step_ids)
        graph = {step.id: set(step.depends_on_step_ids) for step in self.steps}
        if any(
            dependency not in known or dependency == step_id
            for step_id, dependencies in graph.items()
            for dependency in dependencies
        ):
            raise ValueError("flow step dependency reference is invalid")
        if any(
            source.source_step_id not in known
            or source.source_step_id not in graph[step.id]
            for step in self.steps
            for source in step.variable_sources
        ):
            raise ValueError("flow variable source must be a declared dependency")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            """深度遍历单个步骤，在再次进入当前路径时识别依赖环。"""

            if step_id in visiting:
                raise ValueError("flow dependencies must be acyclic")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in graph[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in step_ids:
            visit(step_id)
        return self


# 声明一种攻击关系应由哪些观察面判定，以及问题严重程度。
class ContractRule(DomainModel):
    id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    kind: RuleKind
    required_observers: tuple[Literal["http", "owner_api"], ...] = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"] = "high"


# 汇总可执行关系规则；输入边界只允许 ACTIVE 契约进入运行。
class SecurityContract(DomainModel):
    id: str = Field(pattern=LONG_SLUG_ID_PATTERN)
    version: int = Field(default=1, ge=1)
    status: ContractStatus = ContractStatus.ACTIVE
    rules: tuple[ContractRule, ...] = Field(min_length=1)


# 保存项目目标、身份、资源、输入文件位置和默认变异 seed。
class ProjectDefinition(DomainModel):
    id: str = Field(pattern=PROJECT_ID_PATTERN)
    name: str = Field(min_length=1, max_length=128)
    target: TargetScope
    identities: tuple[Identity, ...] = Field(min_length=2)
    resources: tuple[ResourceDefinition, ...] = Field(min_length=2)
    flow_path: Path
    contract_path: Path
    owner_observer_enabled: bool = True
    mutation_seed: int = 7


# 保存由正常 FlowStep 派生的攻击请求；step_id/rule_id 保留来源与判定规则。
# 执行器通过 step_id 回到原步骤执行基线，再发送本对象描述的攻击版本。
class MutationCase(DomainModel):
    case_id: str
    fingerprint: str
    step_id: str
    rule_id: str
    mutation: MutationKind
    method: str
    path: str
    identity_id: str
    resource_id: str
    owner_identity_id: str
    json_body: dict[str, Any] = Field(default_factory=dict)


# 汇总固定 seed 和引擎版本下确定生成的全部 MutationCase。
class MutationPlan(DomainModel):
    seed: int
    engine_version: str
    cases: tuple[MutationCase, ...]


# 记录某个阶段从 HTTP 或资源所有者视角看到的事实。
class Observation(DomainModel):
    observer: Literal["http", "owner_api"]
    phase: Literal["initial", "baseline", "before", "mutation", "after"]
    status_code: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


# 把攻击用例、观察事实、判定原因和内容哈希固化为单条证据。
class Evidence(DomainModel):
    evidence_id: str
    run_id: str
    case_id: str
    fingerprint: str
    rule_id: str
    mutation: MutationKind
    verdict: CaseVerdict
    reason_codes: tuple[str, ...]
    request: dict[str, Any]
    observations: tuple[Observation, ...]
    evidence_hash: str


# 汇总一次验证的总体结论、全部证据和工件目录。
class RunResult(DomainModel):
    run_id: str
    project_id: str
    engine_version: str
    verdict: RunVerdict
    reason_codes: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    artifact_dir: str
