# =============================================================================
# HTTP 身份运行时
#
# 定位
#   受控 HTTP Adapter 内的单身份、单 case 认证状态边界。
#
# 职责
#   解析受控 secret ref｜隔离内存 Cookie｜注入认证头｜限制 Bootstrap/Refresh
#
# 边界
#   不写 Profile、Evidence 或日志，不读取浏览器/系统代理，不把 Bootstrap
#   当作业务请求；身份准备失败时禁止匿名继续。
#
# 调用链
#   Runner → HttpIdentityRuntime → HttpExecutionAdapter / httpx.Client
# =============================================================================

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.web.identity import (
    BearerIdentityBinding,
    CookieSessionIdentityBinding,
    HttpIdentityBinding,
    HttpIdentityKind,
    LoginWorkflowIdentityBinding,
    OAuth2ClientCredentialsIdentityBinding,
    OAuth2RefreshTokenIdentityBinding,
    StaticHeadersIdentityBinding,
)


SecretResolver = Callable[[str], str | None]
BootstrapSender = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class IdentityTokenState:
    access_token: str
    refresh_token: str | None = None


class HttpIdentityRuntime:
    """为一个 identity 建立可销毁的认证状态；实例不得跨 case 复用。"""

    def __init__(
        self,
        binding: HttpIdentityBinding,
        *,
        resolve_secret: SecretResolver,
        business_origin: str,
    ) -> None:
        self.binding = binding
        self._resolve_secret = resolve_secret
        self.business_origin = _normalize_origin(business_origin)
        self.client = httpx.Client(follow_redirects=False, trust_env=False)
        self._bootstrapped = binding.kind in {HttpIdentityKind.BEARER, HttpIdentityKind.STATIC_HEADERS}
        self._token: IdentityTokenState | None = None
        self._refresh_count = 0
        self._csrf_values: dict[str, str] = {}
        self._secret_values: set[str] = set()

    @property
    def cookies(self) -> httpx.Cookies:
        """返回仅属于当前 case 的 Cookie jar；调用方不能持久化它。"""

        return self.client.cookies

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    def redaction_secrets(self) -> tuple[str, ...]:
        # Cookie 值同样是身份秘密；目标回显时必须在离开 HTTP 边界前脱敏。
        cookie_values = {cookie.value for cookie in self.client.cookies.jar if cookie.value}
        return tuple(self._secret_values | set(self._csrf_values.values()) | cookie_values)

    @property
    def bootstrapped(self) -> bool:
        return self._bootstrapped

    def close(self) -> None:
        self.client.cookies.clear()
        self._csrf_values.clear()
        self._secret_values.clear()
        self._token = None
        self.client.close()

    def rebuild(self) -> HttpIdentityRuntime:
        """重建 case 会话，确保 Cookie、Token、CSRF 不跨 case 存活。"""

        self.close()
        return HttpIdentityRuntime(
            self.binding,
            resolve_secret=self._resolve_secret,
            business_origin=self.business_origin,
        )

    def headers_for_request(self, *, origin: str) -> dict[str, str]:
        if _normalize_origin(origin) != self.business_origin:
            raise JiejianError(ErrorCode.SCOPE_HOST, "身份不得向未绑定的业务 origin 注入认证状态")
        if not self._bootstrapped:
            raise JiejianError(ErrorCode.EXEC_REQUEST, "身份 Bootstrap 尚未成功，禁止匿名请求")
        binding = self.binding
        if isinstance(binding, BearerIdentityBinding):
            return {"Authorization": f"Bearer {self._secret(binding.secret_ref)}"}
        if isinstance(binding, StaticHeadersIdentityBinding):
            return {header.name: self._secret(header.secret_ref) for header in binding.headers}
        if self._token is not None:
            return {"Authorization": f"Bearer {self._token.access_token}"}
        return {}

    def bootstrap(self, send: BootstrapSender, *, requests: tuple[Any, ...] = ()) -> None:
        """运行已由上层冻结的 Bootstrap；任一步失败都终止本身份。"""

        if isinstance(self.binding, (BearerIdentityBinding, StaticHeadersIdentityBinding)):
            self._bootstrapped = True
            return
        if isinstance(self.binding, (CookieSessionIdentityBinding, LoginWorkflowIdentityBinding)):
            if not requests:
                raise JiejianError(ErrorCode.EXEC_REQUEST, "Cookie/Login identity 缺少 Bootstrap 请求")
            for request in requests:
                response = send(request, bootstrap=True)
                if not 200 <= int(response.status_code) < 400:
                    self._bootstrapped = False
                    raise JiejianError(ErrorCode.EXEC_REQUEST, "身份 Bootstrap 失败")
            self._bootstrapped = True
            return
        if isinstance(self.binding, OAuth2ClientCredentialsIdentityBinding):
            self._authorize_auth_path(self.binding.token_path, self.binding.auth_scope)
            response = send(
                self.binding.token_path,
                method="POST",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._secret(self.binding.client_id_ref),
                    "client_secret": self._secret(self.binding.client_secret_ref),
                    **({"scope": self.binding.scope} if self.binding.scope else {}),
                },
                auth=True,
                auth_scope=self.binding.auth_scope,
            )
            self._remember_token(_token_from_response(response))
            self._bootstrapped = True
            return
        if isinstance(self.binding, OAuth2RefreshTokenIdentityBinding):
            self._authorize_auth_path(self.binding.token_path, self.binding.auth_scope)
            refresh_token = self._current_refresh_token()
            response = send(
                self.binding.token_path,
                method="POST",
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._secret(self.binding.client_id_ref),
                    "refresh_token": refresh_token,
                },
                auth=True,
                auth_scope=self.binding.auth_scope,
            )
            token = _token_from_response(response)
            self._remember_token(
                token
                if token.refresh_token is not None
                else IdentityTokenState(access_token=token.access_token, refresh_token=refresh_token)
            )
            self._bootstrapped = True
            return
        raise JiejianError(ErrorCode.EXEC_REQUEST, "未知身份绑定")

    def _secret(self, secret_ref: str) -> str:
        value = _required_secret(self._resolve_secret, secret_ref)
        self._secret_values.add(value)
        return value

    def _current_refresh_token(self) -> str:
        if self._token is not None and self._token.refresh_token:
            return self._token.refresh_token
        assert isinstance(self.binding, OAuth2RefreshTokenIdentityBinding)
        return self._secret(self.binding.refresh_token_ref)

    def _remember_token(self, token: IdentityTokenState) -> None:
        self._token = token
        self._secret_values.add(token.access_token)
        if token.refresh_token:
            self._secret_values.add(token.refresh_token)

    def _authorize_auth_path(self, path: str, scope: Any) -> None:
        if not path.startswith("/") or path.startswith("//"):
            raise JiejianError(ErrorCode.SCOPE_URL, "身份端点必须是相对路径")
        parsed = urlsplit(scope.base_url + path)
        origin = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"
        if origin not in scope.allowed_origins or parsed.hostname not in scope.allowed_hosts or (parsed.port or (443 if parsed.scheme == 'https' else 80)) not in scope.allowed_ports:
            raise JiejianError(ErrorCode.SCOPE_HOST, "身份端点越出 AuthTargetScope")

    def refresh_once(self, send: BootstrapSender, *, token_expired: bool) -> bool:
        """只接受显式 token-expired 事实，并最多刷新一次。"""

        if not token_expired or self._refresh_count >= 1:
            return False
        if not isinstance(self.binding, OAuth2RefreshTokenIdentityBinding):
            return False
        self._refresh_count += 1
        self._bootstrapped = False
        self.bootstrap(send)
        return True

    def set_csrf(self, slot_id: str, value: str, *, origin: str, max_length: int) -> None:
        if _normalize_origin(origin) != self.business_origin:
            raise JiejianError(ErrorCode.SCOPE_HOST, "CSRF 来源 origin 越界")
        if not value or len(value) > max_length or any(ord(char) < 0x20 for char in value):
            raise JiejianError(ErrorCode.EXEC_REQUEST, "CSRF 值超出受控长度或字符范围")
        self._csrf_values[slot_id] = value

    def slot_value(self, slot_id: str) -> str | None:
        return self._csrf_values.get(slot_id)


def _required_secret(resolve_secret: SecretResolver, secret_ref: str) -> str:
    value = resolve_secret(secret_ref)
    if not value:
        raise JiejianError(ErrorCode.SECRET_MISSING, "身份秘密不可用")
    return value


def _normalize_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise JiejianError(ErrorCode.SCOPE_URL, "身份 origin 无效")
    return f"{parsed.scheme}://{parsed.hostname.lower()}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"


def _token_from_response(response: Any) -> IdentityTokenState:
    if not 200 <= int(response.status_code) < 300:
        raise JiejianError(ErrorCode.EXEC_REQUEST, "OAuth token endpoint 返回失败")
    try:
        if hasattr(response, "json"):
            payload = response.json()
        elif hasattr(response, "body") and response.body:
            payload = json.loads(response.body)
        else:
            payload = response.data
    except (ValueError, TypeError, json.JSONDecodeError):
        raise JiejianError(ErrorCode.EXEC_REQUEST, "OAuth token 响应无效") from None
    if not isinstance(payload, Mapping) or not isinstance(payload.get("access_token"), str) or not payload["access_token"]:
        raise JiejianError(ErrorCode.EXEC_REQUEST, "OAuth token 响应缺少 access_token")
    refresh = payload.get("refresh_token")
    if refresh is not None and not isinstance(refresh, str):
        raise JiejianError(ErrorCode.EXEC_REQUEST, "OAuth refresh_token 类型无效")
    return IdentityTokenState(access_token=payload["access_token"], refresh_token=refresh)
