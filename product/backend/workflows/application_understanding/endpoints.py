# =============================================================================
# 本地应用地址发现
#
# 定位
#   受限目录识别之后、用户确认应用访问授权之前的 loopback 候选服务
#
# 职责
#   解析受控配置字面量｜规范化本机地址｜按固定优先级和请求预算探测候选
#
# 边界
#   不扫描任意端口、不启动用户项目、不携带凭据，也不跟随离开 loopback 的重定向。
#
# 调用链
#   Application Understanding service → TargetEndpointDiscovery → 配置文件 / 本机 HTTP(S)
# =============================================================================

from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import socket
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.onboarding.discovery import (
    canonical_folder,
    discover_folder,
    is_reparse_point,
)


_CONFIG_NAMES = frozenset(
    {
        "angular.json",
        "astro.config.js",
        "astro.config.mjs",
        "astro.config.ts",
        "next.config.js",
        "next.config.mjs",
        "next.config.ts",
        "nuxt.config.js",
        "nuxt.config.ts",
        "openapi.json",
        "openapi.yaml",
        "openapi.yml",
        "package.json",
        "swagger.json",
        "swagger.yaml",
        "swagger.yml",
        "vite.config.js",
        "vite.config.mjs",
        "vite.config.ts",
    }
)
_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".next",
        ".nuxt",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "var",
        "venv",
    }
)
_URL_LITERAL = re.compile(r"https?://(?:localhost|127\.0\.0\.1)(?::\d{1,5})?(?:/[A-Za-z0-9._~!$&'()*+,;=:@%{}\-/]*)?", re.IGNORECASE)
_PORT_LITERAL = re.compile(r"\bport\s*[:=]\s*[\"']?(\d{1,5})", re.IGNORECASE)
_COMMAND_PORT = re.compile(r"(?:^|\s)(?:--port(?:=|\s+)|-p\s+)(\d{1,5})(?=\s|$)", re.IGNORECASE)
_SOURCE_RANK = {"CONFIG": 0, "OPENAPI": 0, "STARTUP": 1, "FRAMEWORK_DEFAULT": 2}
_FRAMEWORK_DEFAULTS = {
    "Angular": 4200,
    "Astro": 4321,
    "Django": 8000,
    "Next.js": 3000,
    "Nuxt": 3000,
    "Vite": 5173,
}


class EndpointModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        hide_input_in_errors=True,
    )


class EndpointDiscoveryLimits(EndpointModel):
    max_depth: int = Field(default=2, ge=0, le=2)
    max_entries: int = Field(default=256, ge=1, le=256)
    max_files: int = Field(default=64, ge=1, le=64)
    max_file_bytes: int = Field(default=262_144, ge=1, le=262_144)
    max_total_bytes: int = Field(default=1_048_576, ge=1, le=1_048_576)
    max_candidates: int = Field(default=16, ge=1, le=16)
    max_requests: int = Field(default=8, ge=1, le=8)
    timeout_seconds: float = Field(default=0.5, ge=0.1, le=2.0)
    max_response_bytes: int = Field(default=4096, ge=256, le=16_384)


class EndpointProbeObservation(EndpointModel):
    reachable: bool
    status_code: int | None = Field(default=None, ge=100, le=599)
    detail: str = Field(min_length=1, max_length=128)


class EndpointCandidate(EndpointModel):
    endpoint: str = Field(min_length=1, max_length=2048)
    source_type: Literal["CONFIG", "OPENAPI", "STARTUP", "FRAMEWORK_DEFAULT"]
    source: str = Field(min_length=1, max_length=256)
    rank: int = Field(ge=0, le=2)
    reachable: bool
    status_code: int | None = Field(default=None, ge=100, le=599)
    probe_detail: str = Field(min_length=1, max_length=128)
    confirmation_required: Literal[True] = True


class EndpointDiscoveryResult(EndpointModel):
    source_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[EndpointCandidate, ...] = Field(default=(), max_length=16)
    request_count: int = Field(ge=0, le=8)
    default_endpoint: str | None = Field(default=None, min_length=1, max_length=2048)
    manual_entry_required: bool


ProbeFunction = Callable[[str, EndpointDiscoveryLimits], EndpointProbeObservation]


def normalize_loopback_endpoint(value: str) -> str:
    """将明确 localhost 规范为 loopback，并拒绝任何非本机授权范围。"""

    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        if parsed.query or parsed.fragment:
            raise ValueError
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (AttributeError, TypeError, ValueError):
        raise JiejianError(
            ErrorCode.APPLICATION_ENDPOINT_INVALID,
            "本地应用地址必须是完整的 HTTP(S) loopback 地址",
        ) from None
    host = parsed.hostname.casefold()
    if host == "localhost":
        try:
            resolved = {
                item[4][0]
                for item in socket.getaddrinfo(
                    "localhost",
                    port,
                    type=socket.SOCK_STREAM,
                )
            }
        except OSError:
            raise JiejianError(
                ErrorCode.APPLICATION_ENDPOINT_INVALID,
                "localhost 无法安全解析为本机地址",
            ) from None
        if not resolved or not resolved.issubset({"127.0.0.1", "::1"}):
            raise JiejianError(
                ErrorCode.APPLICATION_ENDPOINT_INVALID,
                "localhost 解析结果超出 loopback 范围",
            )
        if "127.0.0.1" not in resolved:
            raise JiejianError(
                ErrorCode.APPLICATION_ENDPOINT_INVALID,
                "当前 Web 执行仅支持 IPv4 loopback，请使用 127.0.0.1 启动应用",
            )
        host = "127.0.0.1"
    if host == "::1":
        raise JiejianError(
            ErrorCode.APPLICATION_ENDPOINT_INVALID,
            "当前 Web 执行仅支持 IPv4 loopback，请使用 127.0.0.1 启动应用",
        )
    if host != "127.0.0.1":
        raise JiejianError(
            ErrorCode.APPLICATION_ENDPOINT_INVALID,
            "自动接入只允许 127.0.0.1 或安全解析的 localhost",
        )
    authority = f"{host}:{port}"
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, authority, path, "", ""))


class TargetEndpointDiscovery:
    """提取固定来源候选并执行无凭据、无外部重定向的小预算探测。"""

    def __init__(
        self,
        *,
        limits: EndpointDiscoveryLimits | None = None,
        probe: ProbeFunction | None = None,
    ) -> None:
        self.limits = limits or EndpointDiscoveryLimits()
        self._probe = probe or self._request_endpoint

    def discover(self, source_root: str | Path) -> EndpointDiscoveryResult:
        root = canonical_folder(source_root)
        discovery = discover_folder(root)
        files, fingerprint = self._configuration_files(root)
        extracted: dict[str, tuple[str, str]] = {}

        def add(raw: str, source_type: str, source: str) -> None:
            try:
                endpoint = normalize_loopback_endpoint(raw)
            except JiejianError:
                return
            current = extracted.get(endpoint)
            if current is None or _SOURCE_RANK[source_type] < _SOURCE_RANK[current[0]]:
                extracted[endpoint] = (source_type, source[:256])

        for relative, text in files:
            lower_name = Path(relative).name.casefold()
            if lower_name in {"openapi.json", "swagger.json", "openapi.yaml", "openapi.yml", "swagger.yaml", "swagger.yml"}:
                for server in self._openapi_servers(text, lower_name.endswith("json")):
                    add(server, "OPENAPI", f"{relative}:servers")
            if lower_name == "package.json":
                try:
                    package = json.loads(text)
                except json.JSONDecodeError:
                    package = None
                if isinstance(package, dict):
                    scripts = package.get("scripts")
                    if isinstance(scripts, dict):
                        for name in sorted(scripts):
                            command = scripts[name]
                            if not isinstance(name, str) or not isinstance(command, str):
                                continue
                            self._extract_command(command, f"{relative}:scripts.{name}", add)
                    for port in self._json_ports(package):
                        add(f"http://127.0.0.1:{port}", "CONFIG", relative)
            if lower_name != "package.json":
                for match in _URL_LITERAL.finditer(text):
                    add(match.group(0), "CONFIG", relative)
                for match in _PORT_LITERAL.finditer(text):
                    add(f"http://127.0.0.1:{match.group(1)}", "CONFIG", relative)

        for detected_type in discovery.detected_types:
            port = _FRAMEWORK_DEFAULTS.get(detected_type)
            if port is not None:
                add(
                    f"http://127.0.0.1:{port}",
                    "FRAMEWORK_DEFAULT",
                    f"{detected_type} 标准开发端口",
                )

        ordered = sorted(
            extracted.items(),
            key=lambda item: (_SOURCE_RANK[item[1][0]], item[0], item[1][1]),
        )[: self.limits.max_candidates]
        candidates: list[EndpointCandidate] = []
        request_count = 0
        for endpoint, (source_type, source) in ordered:
            if request_count < self.limits.max_requests:
                observation = self._probe(endpoint, self.limits)
                request_count += 1
            else:
                observation = EndpointProbeObservation(
                    reachable=False,
                    detail="未探测：已达到请求预算",
                )
            candidates.append(
                EndpointCandidate(
                    endpoint=endpoint,
                    source_type=source_type,
                    source=source,
                    rank=_SOURCE_RANK[source_type],
                    reachable=observation.reachable,
                    status_code=observation.status_code,
                    probe_detail=observation.detail,
                )
            )
        reachable = [item.endpoint for item in candidates if item.reachable]
        return EndpointDiscoveryResult(
            source_fingerprint=fingerprint,
            candidates=tuple(candidates),
            request_count=request_count,
            default_endpoint=reachable[0] if len(reachable) == 1 else None,
            manual_entry_required=not reachable,
        )

    def source_fingerprint(self, source_root: str | Path) -> str:
        root = canonical_folder(source_root)
        _, fingerprint = self._configuration_files(root)
        return fingerprint

    def probe(self, endpoint: str) -> tuple[str, EndpointProbeObservation]:
        normalized = normalize_loopback_endpoint(endpoint)
        return normalized, self._probe(normalized, self.limits)

    def _configuration_files(self, root: Path) -> tuple[tuple[tuple[str, str], ...], str]:
        entries_seen = 0
        files_seen = 0
        total_bytes = 0
        values: list[tuple[str, str]] = []
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            directory, depth = stack.pop()
            try:
                entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
            except OSError:
                continue
            for entry in entries:
                entries_seen += 1
                if entries_seen > self.limits.max_entries:
                    raise JiejianError(ErrorCode.ONBOARDING_READ_BUDGET, "本地地址配置识别超过条目预算")
                path = Path(entry.path)
                try:
                    if is_reparse_point(path):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name.casefold() not in _IGNORED_DIRECTORIES and depth < self.limits.max_depth:
                            stack.append((path, depth + 1))
                        continue
                    if not entry.is_file(follow_symlinks=False) or entry.name.casefold() not in _CONFIG_NAMES:
                        continue
                    canonical = path.resolve(strict=True)
                    if canonical != root and root not in canonical.parents:
                        continue
                    size = canonical.stat().st_size
                except (OSError, RuntimeError, ValueError):
                    continue
                files_seen += 1
                total_bytes += size
                if (
                    files_seen > self.limits.max_files
                    or size > self.limits.max_file_bytes
                    or total_bytes > self.limits.max_total_bytes
                ):
                    raise JiejianError(ErrorCode.ONBOARDING_READ_BUDGET, "本地地址配置识别超过读取预算")
                try:
                    text = canonical.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                relative = canonical.relative_to(root).as_posix()
                values.append((relative, text))
        values.sort(key=lambda item: item[0].casefold())
        digest = hashlib.sha256()
        for relative, text in values:
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(text.encode("utf-8")).digest())
        return tuple(values), digest.hexdigest()

    @staticmethod
    def _openapi_servers(text: str, is_json: bool) -> tuple[str, ...]:
        try:
            document = json.loads(text) if is_json else yaml.safe_load(text)
        except (json.JSONDecodeError, yaml.YAMLError):
            return ()
        if not isinstance(document, dict) or not (
            "openapi" in document or "swagger" in document
        ):
            return ()
        servers = document.get("servers")
        if not isinstance(servers, list):
            return ()
        return tuple(
            item["url"]
            for item in servers[:16]
            if isinstance(item, dict) and isinstance(item.get("url"), str)
        )

    @staticmethod
    def _json_ports(value: object) -> Iterable[int]:
        pending = [value]
        seen = 0
        while pending and seen < 256:
            item = pending.pop()
            seen += 1
            if isinstance(item, dict):
                for key, nested in item.items():
                    if str(key).casefold() in {"port", "default_port"} and isinstance(nested, int) and 1 <= nested <= 65535:
                        yield nested
                    elif isinstance(nested, (dict, list)):
                        pending.append(nested)
            elif isinstance(item, list):
                pending.extend(value for value in item if isinstance(value, (dict, list)))

    @staticmethod
    def _extract_command(command: str, source: str, add: Callable[[str, str, str], None]) -> None:
        for match in _URL_LITERAL.finditer(command):
            add(match.group(0), "STARTUP", source)
        for match in _COMMAND_PORT.finditer(command):
            add(f"http://127.0.0.1:{match.group(1)}", "STARTUP", source)

    @staticmethod
    def _request_endpoint(
        endpoint: str,
        limits: EndpointDiscoveryLimits,
    ) -> EndpointProbeObservation:
        parsed = urlsplit(endpoint)
        connection_type = (
            http.client.HTTPSConnection
            if parsed.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_type(
            parsed.hostname,
            parsed.port,
            timeout=limits.timeout_seconds,
        )
        try:
            connection.request(
                "GET",
                parsed.path or "/",
                headers={"Accept": "text/html,application/json", "User-Agent": "Jiejian-Endpoint-Discovery"},
            )
            response = connection.getresponse()
            response.read(limits.max_response_bytes)
            if 300 <= response.status < 400:
                location = response.getheader("Location")
                if location:
                    redirected = urljoin(endpoint + "/", location)
                    try:
                        normalize_loopback_endpoint(redirected)
                    except JiejianError:
                        return EndpointProbeObservation(
                            reachable=False,
                            status_code=response.status,
                            detail="重定向离开 loopback，已拒绝",
                        )
            return EndpointProbeObservation(
                reachable=True,
                status_code=response.status,
                detail="本地服务已响应",
            )
        except (OSError, TimeoutError, http.client.HTTPException):
            return EndpointProbeObservation(
                reachable=False,
                detail="本地服务未在探测预算内响应",
            )
        finally:
            connection.close()
