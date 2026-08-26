# =============================================================================
# 测试身份 headed browser 适配器
#
# 定位
#   独立身份准备进程中的 Playwright、网络安全和 SecretStore 边界。
#
# 职责
#   启动独立 BrowserContext｜限制每个请求到确认目标｜捕获受限 Cookie 或 Bearer 状态。
#
# 边界
#   不生成 RecordingEvent，不保存密码、localStorage、storage_state、历史或其他主机 Cookie。
#
# 调用链
#   identity_preparation_process → adapter → Playwright / BoundedRouteTransport / SecretStore
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlsplit

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Playwright,
    Page,
    Route,
    sync_playwright,
)

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.core.test_identity import TestIdentityAuthMethod
from product.backend.infra.execution.web.adapter import WebTargetGuard
from product.backend.infra.recording.transport import BoundedRouteTransport
from product.backend.infra.secrets import SecretStore, credential_ref
from product.protocols import (
    IdentityPreparationRequest,
    IdentityPreparationResult,
    IdentityPreparationResultType,
    PreparedCookieRef,
)
from product.protocols.web.target import WebTargetDefinition


_CREDENTIAL_SECRET_MAX_BYTES = 2_560


class IdentityPreparationBrowserAdapter:
    """只在用户明确确认后把当前目标的最小登录状态写入 SecretStore。"""

    def run(
        self,
        request: IdentityPreparationRequest,
        *,
        secret_store: SecretStore,
        ready_callback: Callable[[], None],
        save_requested: Callable[[], bool],
        cancellation_requested: Callable[[], bool],
        before_secret_write: Callable[[tuple[str, ...]], None] = lambda _refs: None,
        interaction: Callable[[Page], None] | None = None,
        error_observer: Callable[[BaseException], None] | None = None,
        now_us: Callable[[], int] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> IdentityPreparationResult:
        clock = now_us or (lambda: time.time_ns() // 1_000)
        playwright: Playwright | None = None
        browser: Browser | None = None
        context: BrowserContext | None = None
        bearer_tokens: set[str] = set()
        safety_error: JiejianError | None = None
        requests_used = 0
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(
                accept_downloads=False,
                service_workers="block",
            )
            timeout_ms = request.target_scope.timeout_seconds * 1_000
            context.set_default_timeout(timeout_ms)
            context.set_default_navigation_timeout(timeout_ms)
            guard = WebTargetGuard(
                WebTargetDefinition(scope=request.target_scope, reset_path="/reset")
            )
            transport = BoundedRouteTransport(request.target_scope)

            def route_request(route: Route) -> None:
                nonlocal requests_used, safety_error
                try:
                    if requests_used >= request.target_scope.max_requests:
                        raise JiejianError(
                            ErrorCode.EXEC_BUDGET,
                            "测试账号登录浏览器请求预算已耗尽",
                        )
                    requests_used += 1
                    guard.authorize_url(route.request.url)
                    self._capture_bearer(
                        route.request.url,
                        route.request.headers,
                        request.target_scope.allowed_origins[0],
                        bearer_tokens,
                    )
                    response = transport.fetch(route.request, context, guard)
                    route.fulfill(
                        status=response.status_code,
                        headers=response.headers,
                        body=response.body,
                    )
                except JiejianError as exc:
                    safety_error = exc
                    route.abort("blockedbyclient")

            context.route("**/*", route_request)
            context.route_web_socket("**/*", lambda route: route.close())
            page = context.new_page()
            page.goto(request.target_scope.base_url)
            ready_callback()
            if interaction is not None:
                interaction(page)
            deadline = monotonic() + request.timeout_us / 1_000_000
            while True:
                if cancellation_requested() or page.is_closed():
                    return self._terminal(
                        request,
                        IdentityPreparationResultType.CANCELLED,
                    )
                if safety_error is not None:
                    raise safety_error
                if save_requested():
                    break
                if monotonic() >= deadline:
                    return self._failed(request, ErrorCode.EXEC_TIMEOUT.value)
                page.wait_for_timeout(100)
            if safety_error is not None:
                raise safety_error
            return self._capture_login_state(
                request,
                context,
                bearer_tokens,
                secret_store,
                prepared_at_us=clock(),
                before_secret_write=before_secret_write,
                error_observer=error_observer,
            )
        except PlaywrightError as exc:
            observed: BaseException = safety_error or exc
            if error_observer is not None:
                error_observer(observed)
            error_code = (
                safety_error.code
                if safety_error is not None
                else ErrorCode.IDENTITY_PREPARATION_FAILED.value
            )
            return self._failed(request, error_code)
        except JiejianError as exc:
            if error_observer is not None:
                error_observer(exc)
            return self._failed(request, exc.code)
        except (OSError, RuntimeError, ValueError) as exc:
            if error_observer is not None:
                error_observer(exc)
            return self._failed(request, ErrorCode.IDENTITY_PREPARATION_FAILED.value)
        finally:
            self._close(playwright, browser, context)

    def _capture_login_state(
        self,
        request: IdentityPreparationRequest,
        context: BrowserContext,
        bearer_tokens: set[str],
        secret_store: SecretStore,
        *,
        prepared_at_us: int,
        before_secret_write: Callable[[tuple[str, ...]], None],
        error_observer: Callable[[BaseException], None] | None = None,
    ) -> IdentityPreparationResult:
        target_host = urlsplit(request.target_scope.base_url).hostname or ""
        raw_cookies = sorted(
            (
                cookie
                for cookie in context.cookies()
                if str(cookie.get("domain", "")).lstrip(".").casefold()
                == target_host.casefold()
            ),
            key=lambda item: (
                str(item.get("name", "")),
                str(item.get("domain", "")),
                str(item.get("path", "/")),
            ),
        )
        if (
            len(raw_cookies) > 32
            or len(bearer_tokens) > 1
            or bool(raw_cookies and bearer_tokens)
        ):
            return self._terminal(request, IdentityPreparationResultType.UNSUPPORTED)
        written_refs: list[str] = []
        try:
            if raw_cookies:
                planned_refs = tuple(
                    credential_ref(
                        "test-identity",
                        request.project_id,
                        request.identity_id,
                        f"cookie-{ordinal:02d}",
                    )
                    for ordinal in range(len(raw_cookies))
                )
                prepared_cookies: list[tuple[PreparedCookieRef, str]] = []
                for ordinal, raw in enumerate(raw_cookies):
                    value = raw.get("value")
                    if (
                        not isinstance(value, str)
                        or not value
                        or len(value.encode("utf-8")) > _CREDENTIAL_SECRET_MAX_BYTES
                    ):
                        return self._terminal(
                            request, IdentityPreparationResultType.UNSUPPORTED
                        )
                    expires = raw.get("expires")
                    expires_at_us = (
                        int(float(expires) * 1_000_000)
                        if isinstance(expires, (int, float)) and float(expires) > 0
                        else None
                    )
                    prepared_cookies.append(
                        (
                            PreparedCookieRef(
                                name=str(raw.get("name", "")),
                                domain=str(raw.get("domain", "")),
                                path=str(raw.get("path", "/")),
                                secure=bool(raw.get("secure", False)),
                                http_only=bool(raw.get("httpOnly", False)),
                                same_site=str(
                                    raw.get("sameSite", "Lax")
                                ).upper(),
                                expires_at_us=expires_at_us,
                                value_secret_ref=planned_refs[ordinal],
                            ),
                            value,
                        )
                    )
                # 先验证全部元数据，再登记精确补偿计划并逐项写入秘密。
                before_secret_write(planned_refs)
                for cookie, value in prepared_cookies:
                    secret_store.write(cookie.value_secret_ref, value)
                    written_refs.append(cookie.value_secret_ref)
                return IdentityPreparationResult(
                    schema_version="1",
                    preparation_id=request.preparation_id,
                    project_id=request.project_id,
                    identity_id=request.identity_id,
                    result_type=IdentityPreparationResultType.PREPARED,
                    auth_method=TestIdentityAuthMethod.COOKIE_SESSION,
                    cookies=tuple(cookie for cookie, _value in prepared_cookies),
                    prepared_at_us=prepared_at_us,
                )
            if bearer_tokens:
                token = next(iter(bearer_tokens))
                if len(token.encode("utf-8")) > _CREDENTIAL_SECRET_MAX_BYTES:
                    return self._terminal(
                        request, IdentityPreparationResultType.UNSUPPORTED
                    )
                secret_ref = credential_ref(
                    "test-identity",
                    request.project_id,
                    request.identity_id,
                    "bearer",
                )
                before_secret_write((secret_ref,))
                secret_store.write(secret_ref, token)
                written_refs.append(secret_ref)
                return IdentityPreparationResult(
                    schema_version="1",
                    preparation_id=request.preparation_id,
                    project_id=request.project_id,
                    identity_id=request.identity_id,
                    result_type=IdentityPreparationResultType.PREPARED,
                    auth_method=TestIdentityAuthMethod.BEARER,
                    bearer_secret_ref=secret_ref,
                    prepared_at_us=prepared_at_us,
                )
            return self._terminal(request, IdentityPreparationResultType.UNSUPPORTED)
        except (JiejianError, OSError, RuntimeError, ValueError) as exc:
            for secret_ref in written_refs:
                try:
                    secret_store.delete(secret_ref)
                except (JiejianError, OSError, RuntimeError, ValueError):
                    pass
            if error_observer is not None:
                error_observer(exc)
            return self._failed(request, ErrorCode.IDENTITY_PREPARATION_FAILED.value)

    @staticmethod
    def _capture_bearer(
        url: str,
        headers: dict[str, str],
        target_origin: str,
        bearer_tokens: set[str],
    ) -> None:
        parsed = urlsplit(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        origin = f"{parsed.scheme}://{parsed.hostname}:{port}"
        if origin != target_origin:
            return
        authorization = next(
            (
                value
                for name, value in headers.items()
                if name.casefold() == "authorization"
            ),
            "",
        )
        scheme, separator, token = authorization.partition(" ")
        if (
            separator
            and scheme.casefold() == "bearer"
            and token
            and token == token.strip()
            and all(ord(char) >= 32 and char != "\x7f" for char in token)
        ):
            bearer_tokens.add(token)

    @staticmethod
    def _terminal(
        request: IdentityPreparationRequest,
        result_type: IdentityPreparationResultType,
    ) -> IdentityPreparationResult:
        return IdentityPreparationResult(
            schema_version="1",
            preparation_id=request.preparation_id,
            project_id=request.project_id,
            identity_id=request.identity_id,
            result_type=result_type,
        )

    @staticmethod
    def _failed(
        request: IdentityPreparationRequest,
        error_code: str,
    ) -> IdentityPreparationResult:
        return IdentityPreparationResult(
            schema_version="1",
            preparation_id=request.preparation_id,
            project_id=request.project_id,
            identity_id=request.identity_id,
            result_type=IdentityPreparationResultType.FAILED,
            error_code=error_code,
        )

    @staticmethod
    def _close(
        playwright: Playwright | None,
        browser: Browser | None,
        context: BrowserContext | None,
    ) -> None:
        if context is not None:
            try:
                context.close(reason="identity-preparation-finished")
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close(reason="identity-preparation-finished")
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
