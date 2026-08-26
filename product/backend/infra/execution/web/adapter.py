# =============================================================================
# Verification HTTP 执行
#
# 定位
#   所有 Verification 目标请求的受控网络适配器
#
# 职责
#   逐次目标授权｜请求与响应预算｜重定向、超时和取消处理
#
# 边界
#   只实现 Web 目标的网络细节，不决定 Permission、Verification 或 Finding 结论
#
# 调用链
#   Runner → HttpExecutionAdapter → TargetGuard / httpx
# =============================================================================

from __future__ import annotations

import html.parser
import json
import ipaddress
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from urllib.parse import quote, urljoin, urlsplit

import httpx

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.redaction import redact_known_secrets
from product.backend.core.verification.facts import ExecutionFact, ExecutionOutcome, TargetType
from product.protocols.web.identity import AuthTargetScope
from product.protocols.web.target import WebTargetDefinition
from product.protocols.web.workflow import (
    EmptyBody,
    FormUrlEncodedBody,
    HTTP_TEMPLATE_MAX_BYTES,
    HttpOutcome,
    HttpOutcomeClassifier,
    HttpParameter,
    HttpRequestTemplate,
    JsonBody,
    MultipartBody,
    ResponseExtractor,
    ResponseExtractorKind,
    ValueSlot,
)

if TYPE_CHECKING:
    from product.backend.infra.execution.web.identity import HttpIdentityRuntime

_METADATA_ADDRESSES = {
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("100.100.100.200"),
    ipaddress.ip_address("fd00:ec2::254"),
}
_EXPLICIT_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8", "fc00::/7", "::1/128")
)


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """保存目标返回的状态码和已解析、已脱敏响应数据。"""

    status_code: int
    data: dict[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    url: str = ""


@dataclass(frozen=True, slots=True)
class AuthorizedTarget:
    url: str
    host: str
    port: int
    addresses: tuple[str, ...]


class WebTargetGuard:
    """在 HTTP 适配器边界内执行 scope、自检、重定向和私网安全校验。"""

    def __init__(
        self,
        target: WebTargetDefinition | AuthTargetScope,
        *,
        reserved_origins: Sequence[str] = (),
    ) -> None:
        self.target = target
        self.scope = target.scope if isinstance(target, WebTargetDefinition) else target
        self.reserved_origins = frozenset(reserved_origins)

    def authorize_path(self, path: str) -> AuthorizedTarget:
        parsed = urlsplit(path)
        if not path.startswith("/") or parsed.scheme or parsed.netloc:
            raise JiejianError(ErrorCode.SCOPE_URL, "请求路径必须是当前目标下的绝对路径引用")
        return self.authorize_url(f"{self.scope.base_url}{path}")

    def authorize_url(self, url: str) -> AuthorizedTarget:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise JiejianError(ErrorCode.SCOPE_URL, "只允许 HTTP 或 HTTPS 目标")
        if parsed.username is not None or parsed.password is not None:
            raise JiejianError(ErrorCode.SCOPE_URL, "目标 URL 不得包含用户信息")
        if parsed.hostname is None:
            raise JiejianError(ErrorCode.SCOPE_URL, "目标 URL 缺少主机")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            raise JiejianError(ErrorCode.SCOPE_PORT, "目标端口无效") from exc
        host = parsed.hostname.lower()
        if host not in self.scope.allowed_hosts:
            raise JiejianError(ErrorCode.SCOPE_HOST, "目标主机不在授权范围")
        if port not in self.scope.allowed_ports:
            raise JiejianError(ErrorCode.SCOPE_PORT, "目标端口不在授权范围")
        origin = f"{parsed.scheme}://{host}:{port}"
        if origin in self.reserved_origins:
            raise JiejianError(
                ErrorCode.SELF_TARGET_FORBIDDEN,
                "执行目标不得指向界鉴自身服务",
            )
        if origin not in self.scope.allowed_origins:
            raise JiejianError(ErrorCode.SCOPE_HOST, "目标 origin 不在授权范围")
        try:
            address = ipaddress.IPv4Address(host)
        except ipaddress.AddressValueError as exc:
            raise JiejianError(ErrorCode.SCOPE_HOST, "可执行目标必须使用 IPv4 字面量") from exc
        if address in _METADATA_ADDRESSES or address.is_link_local or address.is_multicast or address.is_reserved or address.is_unspecified:
            raise JiejianError(ErrorCode.SCOPE_PRIVATE_NETWORK, "目标地址属于禁止访问的本地或元数据范围")
        if not address.is_global and not (
            self.scope.allow_private_network
            and any(address in network for network in _EXPLICIT_PRIVATE_NETWORKS)
        ):
            raise JiejianError(ErrorCode.SCOPE_PRIVATE_NETWORK, "目标地址不属于显式允许的公网、私网或环回范围")
        return AuthorizedTarget(url=url, host=host, port=port, addresses=(str(address),))

    def authorize_redirect(self, current_url: str, location: str) -> AuthorizedTarget:
        try:
            return self.authorize_url(urljoin(current_url, location))
        except JiejianError as exc:
            raise JiejianError(ErrorCode.SCOPE_REDIRECT, "响应重定向目标越出授权范围", details={"cause": exc.code}) from exc


class HttpExecutionAdapter:
    """作为 Verification 唯一主动 HTTP 边界，统一执行授权和资源限制。"""

    def __init__(
        self,
        target: WebTargetDefinition,
        *,
        cleanup_reserve: int = 0,
        known_secrets: tuple[str, ...] = (),
        cancellation_requested: Callable[[], bool] | None = None,
        executor_process_id: int | None = None,
        fixture_artifacts: Mapping[str, bytes] | None = None,
        reserved_origins: Sequence[str] = (),
    ) -> None:
        """创建不读取代理环境、不自动跟随重定向的有界 HTTP 客户端。

        关键说明
            cleanup_reserve 从总请求预算中提前留给清理操作；known_secrets 只在内存中
            用于响应脱敏，不会写入请求结果或工件。
        """

        self.target_type = TargetType.WEB
        self.guard = WebTargetGuard(target, reserved_origins=reserved_origins)
        self.requests_used = 0
        self.auth_requests_used: dict[str, int] = {}
        self.cleanup_reserve = cleanup_reserve
        self.known_secrets = known_secrets
        self.cancellation_requested = cancellation_requested or (lambda: False)
        self.executor_process_id = executor_process_id
        self.fixture_artifacts = dict(fixture_artifacts or {})
        self.client = httpx.Client(
            follow_redirects=False,
            timeout=target.scope.timeout_seconds,
            trust_env=False,
        )

    def close(self) -> None:
        """关闭底层 httpx 客户端并释放连接资源。"""

        self.client.close()

    def execute(
        self,
        binding: HttpRequestTemplate,
        *,
        case_id: str,
        action_id: str,
        classifier: HttpOutcomeClassifier | None = None,
        slot_values: Mapping[str, Any] | None = None,
        identity_runtime: HttpIdentityRuntime | None = None,
        terminal_completed: bool | None = None,
    ) -> ExecutionFact:
        """执行冻结请求模板，并把分类结果归约到既有 ExecutionFact。"""

        fact, _response = self.execute_detailed(
            binding,
            case_id=case_id,
            action_id=action_id,
            classifier=classifier,
            slot_values=slot_values,
            identity_runtime=identity_runtime,
            terminal_completed=terminal_completed,
        )
        return fact

    def execute_detailed(
        self,
        binding: HttpRequestTemplate,
        *,
        case_id: str,
        action_id: str,
        classifier: HttpOutcomeClassifier | None = None,
        slot_values: Mapping[str, Any] | None = None,
        identity_runtime: HttpIdentityRuntime | None = None,
        terminal_completed: bool | None = None,
        cleanup_request: bool = False,
    ) -> tuple[ExecutionFact, HttpResponse]:
        """发送单个模板并返回同一响应，供工作流提取动态值。"""

        values = slot_values or {}
        request_payload = {
            "action_id": action_id,
            "template": binding.model_dump(mode="json"),
            "slots": _non_secret_slot_values(binding.input_slots, values),
        }
        input_hash = _web_json_sha256(request_payload)
        try:
            response = self.request(
                binding.method,
                _render_path(binding.path, values),
                case_id=case_id,
                query=binding.query,
                headers=binding.headers,
                body=binding.body,
                slot_values=values,
                identity_runtime=identity_runtime,
                cleanup_request=cleanup_request,
                redaction_values=tuple(
                    str(values[item.slot_id])
                    for item in binding.input_slots
                    if item.secret and item.slot_id in values
                ),
            )
        except JiejianError:
            # 传输失败必须沿异常链保留具体原因，由 Case/Runner 写入 cause_code。
            raise
        output_hash = _web_json_sha256({"status": response.status_code, "data": response.data})
        resolved = (classifier or HttpOutcomeClassifier()).classify(response, terminal_completed=terminal_completed)
        outcome = ExecutionOutcome(resolved.value)
        return ExecutionFact(
            case_id=case_id,
            action_id=action_id,
            target_type=self.target_type,
            outcome=outcome,
            execution_marker=case_id,
            input_hash=input_hash,
            output_hash=output_hash,
            reason_codes=() if outcome is not ExecutionOutcome.UNKNOWN else ("UNINTERPRETED_RESPONSE",),
        ), response

    def cleanup(self, path: str, *, case_id: str) -> None:
        response = self.request("POST", path, case_id=case_id, cleanup_request=True, test_mode=True)
        if not 200 <= response.status_code < 300:
            raise JiejianError(
                ErrorCode.RECOVERY_UNAVAILABLE,
                "目标恢复端点未接受恢复请求",
            )

    def request(
        self,
        method: str,
        path: str,
        *,
        case_id: str,
        json_body: dict[str, Any] | None = None,
        query: Sequence[HttpParameter] | Mapping[str, str] = (),
        headers: Sequence[HttpParameter] | Mapping[str, str] = (),
        data: Mapping[str, str] | Sequence[tuple[str, str]] | None = None,
        body: EmptyBody | JsonBody | FormUrlEncodedBody | MultipartBody | None = None,
        slot_values: Mapping[str, Any] | None = None,
        identity_runtime: HttpIdentityRuntime | None = None,
        bootstrap_request: bool = False,
        auth_scope: AuthTargetScope | None = None,
        redaction_values: Sequence[str] = (),
        cleanup_request: bool = False,
        test_mode: bool = False,
    ) -> HttpResponse:
        """在授权、取消和预算限制下发送一次目标请求。

        数据流
            相对路径 → TargetGuard 授权 → 构造因果标记和可选身份头
            → 流式读取有界响应 → 校验重定向 → 脱敏并返回 HttpResponse。

        关键说明
            普通请求收到取消信号后不再发送；清理请求仍可使用预留预算完成恢复。
            客户端不会自动跟随重定向，Location 只用于确认目标没有越出授权范围。

        返回
            包含 HTTP 状态码，以及已限制大小、解析并脱敏的数据对象。
        """

        if not cleanup_request and self.cancellation_requested():
            raise JiejianError(ErrorCode.EXEC_CANCELLED, "运行已请求取消")
        rendered_query = _render_parameters(query, slot_values or {})
        rendered_headers = _render_parameters(headers, slot_values or {})
        guard = self.guard if auth_scope is None else WebTargetGuard(auth_scope)
        target = guard.authorize_path(path)
        # 普通请求不能占用清理预留，保证异常或取消后仍能恢复测试状态。
        if auth_scope is None:
            remaining_for_normal = self.guard.scope.max_requests - self.cleanup_reserve
            if self.requests_used >= self.guard.scope.max_requests or (
                not cleanup_request and self.requests_used >= remaining_for_normal
            ):
                raise JiejianError(ErrorCode.EXEC_BUDGET, "HTTP 请求预算已耗尽")
            self.requests_used += 1
            if cleanup_request and self.cleanup_reserve:
                self.cleanup_reserve -= 1
        else:
            used = self.auth_requests_used.get(auth_scope.base_url, 0)
            if used >= auth_scope.max_requests:
                raise JiejianError(ErrorCode.EXEC_BUDGET, "身份请求预算已耗尽")
            self.auth_requests_used[auth_scope.base_url] = used + 1
        # case ID 贯穿目标请求和样例状态，便于把副作用关联回当前攻击用例。
        request_headers = {"X-Jiejian-Case-ID": case_id}
        if self.executor_process_id is not None:
            request_headers["X-Jiejian-Runner-PID"] = str(self.executor_process_id)
        if identity_runtime is not None and not bootstrap_request and auth_scope is None:
            request_headers.update(identity_runtime.headers_for_request(origin=self.guard.scope.base_url))
        request_headers.update(rendered_headers)
        if test_mode:
            request_headers["X-Jiejian-Test-Mode"] = "1"
        request_kwargs = _render_body(body, json_body=json_body, data=data, slot_values=slot_values or {}, fixture_artifacts=self.fixture_artifacts)
        client = identity_runtime.client if identity_runtime is not None else self.client
        try:
            with client.stream(
                method,
                target.url,
                params=rendered_query,
                headers=request_headers,
                timeout=guard.scope.timeout_seconds,
                **request_kwargs,
            ) as response:
                # 流式累计响应，避免先把超限内容完整读入内存。
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > guard.scope.max_response_bytes:
                        raise JiejianError(
                            ErrorCode.EXEC_RESPONSE_TOO_LARGE,
                            "响应体超过安全预算",
                        )
                location = response.headers.get("location")
                if 300 <= response.status_code < 400 and location:
                    guard.authorize_redirect(target.url, location)
                # 目标可能回显凭据，必须在离开网络边界前完成已知秘密脱敏。
                safe_secrets = tuple(self.known_secrets) + tuple(redaction_values)
                if identity_runtime is not None:
                    safe_secrets += identity_runtime.redaction_secrets()
                safe_content = _redact_bytes(bytes(content), safe_secrets)
                data = redact_known_secrets(_decode_response(safe_content), safe_secrets)
                return HttpResponse(
                    status_code=response.status_code,
                    data=data,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=safe_content,
                    url=target.url,
                )
        except httpx.TimeoutException as exc:
            raise JiejianError(ErrorCode.EXEC_TIMEOUT, "目标请求超时") from exc
        except httpx.ConnectError as exc:
            raise JiejianError(
                ErrorCode.TARGET_UNREACHABLE,
                "目标服务不可达",
            ) from exc
        except httpx.RequestError as exc:
            raise JiejianError(
                ErrorCode.EXEC_REQUEST,
                "目标请求失败",
                details={"reason": type(exc).__name__},
            ) from exc


def _decode_response(content: bytes) -> dict[str, Any]:
    """把响应统一转换为字典；非对象 JSON 和普通文本使用包装字段保存。"""

    if not content:
        return {}
    try:
        decoded = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"text": content.decode("utf-8", errors="replace")}
    return decoded if isinstance(decoded, dict) else {"value": decoded}


class _HtmlValueProbe(html.parser.HTMLParser):
    """只在协议允许的有限选择器内提取首个元素文本或属性。"""

    def __init__(self, selector: str, attribute: str | None) -> None:
        super().__init__(convert_charrefs=True)
        match = re.fullmatch(
            r"([A-Za-z][A-Za-z0-9_-]*)(?:#([A-Za-z][A-Za-z0-9_-]*)|\.([A-Za-z][A-Za-z0-9_-]*)|\[([A-Za-z_:][A-Za-z0-9_.:-]*)\])?",
            selector,
        )
        if match is None:
            raise ValueError("unsupported HTML selector")
        self._tag, self._node_id, self._node_class, self._required_attribute = match.groups()
        self._attribute = attribute.lower() if attribute else None
        self._capturing_tag: str | None = None
        self._text: list[str] = []
        self.value: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.value is not None or self._capturing_tag is not None:
            return
        attributes = {name.lower(): value or "" for name, value in attrs}
        if not self._matches(tag, attributes):
            return
        if self._attribute is not None:
            self.value = attributes.get(self._attribute)
        else:
            self._capturing_tag = tag.lower()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self._capturing_tag == tag.lower():
            self.value = ""
            self._capturing_tag = None

    def handle_data(self, data: str) -> None:
        if self._capturing_tag is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capturing_tag == tag.lower():
            self.value = "".join(self._text).strip()
            self._capturing_tag = None

    def _matches(self, tag: str, attributes: Mapping[str, str]) -> bool:
        if tag.lower() != self._tag.lower():
            return False
        if self._node_id and attributes.get("id") != self._node_id:
            return False
        if self._node_class and self._node_class not in attributes.get("class", "").split():
            return False
        return not self._required_attribute or self._required_attribute.lower() in attributes


def extract_response_value(response: HttpResponse, extractor: ResponseExtractor) -> Any:
    """从已脱敏响应中提取一个有界值；空值和越界值均失败关闭。"""

    if extractor.kind is ResponseExtractorKind.JSON_PATH:
        try:
            document: Any = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "响应 JSON 提取失败") from None
        assert extractor.json_path is not None
        value = _extract_json_path(document, extractor.json_path)
    elif extractor.kind is ResponseExtractorKind.HEADER:
        assert extractor.header_name is not None
        value = response.headers.get(extractor.header_name.lower())
    elif extractor.kind is ResponseExtractorKind.LOCATION:
        value = response.headers.get("location")
    elif extractor.kind is ResponseExtractorKind.COOKIE:
        assert extractor.cookie_name is not None
        value = next((part.split("=", 1)[1].split(";", 1)[0] for part in response.headers.get("set-cookie", "").split(",") if part.strip().startswith(f"{extractor.cookie_name}=")), None)
    else:
        text = response.body.decode("utf-8", errors="replace")
        assert extractor.selector is not None
        try:
            probe = _HtmlValueProbe(extractor.selector, extractor.attribute)
            probe.feed(text[:HTTP_TEMPLATE_MAX_BYTES])
            probe.close()
            value = probe.value
        except (AssertionError, ValueError):
            value = None
    if value is None or value == "":
        raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "响应提取为空")
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    else:
        rendered = str(value)
    if len(rendered) > extractor.max_length:
        raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "响应提取超过长度预算")
    return value


def _extract_json_path(document: Any, path: str) -> Any:
    """执行协议已校验的有限对象键与数组索引路径。"""

    if path == "$":
        return document
    value = document
    tokens = re.findall(
        r"\.([A-Za-z_][A-Za-z0-9_-]{0,63})|\[(?:[\"']([^\"']+)[\"']|([0-9]{1,4}))\]",
        path[1:],
    )
    for dotted, quoted, indexed in tokens:
        if indexed:
            if not isinstance(value, list) or int(indexed) >= len(value):
                raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "响应字段提取为空")
            value = value[int(indexed)]
            continue
        key = dotted or quoted
        if not isinstance(value, Mapping) or key not in value:
            raise JiejianError(ErrorCode.VALUE_EXTRACTION_FAILED, "响应字段提取为空")
        value = value[key]
    return value


def _render_parameters(
    values: Sequence[HttpParameter] | Mapping[str, str],
    slot_values: Mapping[str, Any],
) -> list[tuple[str, str]] | dict[str, str]:
    if isinstance(values, Mapping):
        return {str(key): str(value) for key, value in values.items()}
    rendered: list[tuple[str, str]] = []
    for item in values:
        value = item.literal if item.literal is not None else slot_values.get(item.slot_id or "")
        if value is None:
            raise JiejianError(ErrorCode.EXEC_REQUEST, "请求模板 Slot 未提供值")
        rendered.append((item.name, _bounded_slot_value(value)))
    return rendered


def _render_path(path: str, slot_values: Mapping[str, Any]) -> str:
    def replace(match: Any) -> str:
        slot_id = match.group(1)
        if slot_id not in slot_values:
            raise JiejianError(ErrorCode.EXEC_REQUEST, "路径 Slot 未提供值")
        return quote(_bounded_slot_value(slot_values[slot_id]), safe="")

    return re.sub(r"\{([A-Za-z][A-Za-z0-9_.:-]{0,63})\}", replace, path)


def _render_body(
    body: EmptyBody | JsonBody | FormUrlEncodedBody | MultipartBody | None,
    *,
    json_body: dict[str, Any] | None,
    data: Mapping[str, str] | Sequence[tuple[str, str]] | None,
    slot_values: Mapping[str, Any],
    fixture_artifacts: Mapping[str, bytes],
) -> dict[str, Any]:
    if body is None:
        if data is not None:
            return {"data": data}
        return {"json": json_body if json_body else None}
    if isinstance(body, EmptyBody):
        return {}
    if isinstance(body, JsonBody):
        return {"json": _render_json(body.value, slot_values)}
    if isinstance(body, FormUrlEncodedBody):
        return {"data": dict(_render_parameters(body.fields, slot_values))}
    data: list[tuple[str, str]] = []
    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for part in body.parts:
        if part.fixture_artifact_id is not None:
            artifact = fixture_artifacts.get(part.fixture_artifact_id)
            if artifact is None:
                raise JiejianError(ErrorCode.EXEC_REQUEST, "Multipart fixture/artifact 未登记")
            files.append((part.name, (part.filename or "fixture.bin", artifact, part.content_type or "application/octet-stream")))
        else:
            value = part.literal if part.literal is not None else slot_values.get(part.slot_id or "")
            if value is None:
                raise JiejianError(ErrorCode.EXEC_REQUEST, "Multipart Slot 未提供值")
            if part.filename is None:
                data.append((part.name, _bounded_slot_value(value)))
            else:
                files.append((part.name, (part.filename, _bounded_slot_value(value).encode("utf-8"), part.content_type or "application/octet-stream")))
    result: dict[str, Any] = {"data": data}
    if files:
        result["files"] = files
    return result


def _render_json(value: Any, slot_values: Mapping[str, Any]) -> Any:
    if isinstance(value, Mapping):
        if set(value) == {"$slot"}:
            slot_id = value["$slot"]
            if slot_id not in slot_values:
                raise JiejianError(ErrorCode.EXEC_REQUEST, "JSON Slot 未提供值")
            return _bounded_slot_value(slot_values[slot_id])
        return {str(key): _render_json(child, slot_values) for key, child in value.items()}
    if isinstance(value, list):
        return [_render_json(child, slot_values) for child in value]
    return value


def _bounded_slot_value(value: Any) -> str:
    if isinstance(value, bool):
        rendered = "true" if value else "false"
    elif isinstance(value, (str, int, float)):
        rendered = str(value)
    else:
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(rendered) > 4096:
        raise JiejianError(ErrorCode.EXEC_REQUEST, "请求 Slot 值超过长度预算")
    return rendered


def _non_secret_slot_values(slots: Sequence[ValueSlot], values: Mapping[str, Any]) -> dict[str, Any]:
    secret_ids = {slot.slot_id for slot in slots if slot.secret}
    return {key: value for key, value in values.items() if key not in secret_ids}


def _redact_bytes(content: bytes, known_secrets: Sequence[str]) -> bytes:
    result = content
    for secret in known_secrets:
        if secret:
            result = result.replace(secret.encode("utf-8"), b"[REDACTED]")
    return result


def _web_bytes_sha256(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _web_json_sha256(value: Any) -> str:
    return _web_bytes_sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
