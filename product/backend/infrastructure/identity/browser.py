# 测试身份受控浏览器适配器
# 启动独立 BrowserContext、限制每个请求到确认目标、捕获受限 Cookie 或 Bearer 状态。
# 不生成 RecordingEvent，不保存密码、localStorage、storage_state、历史或其他主机 Cookie。

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

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.domain.identities.models import TestIdentityAuthMethod, IdentityVerificationSnapshot
from product.backend.domain.boundaries.entities import boundary_sha256
from product.backend.infrastructure.execution.web.adapter import WebTargetGuard
from product.backend.infrastructure.recording.transport import BoundedRouteTransport
from product.backend.infrastructure.secrets import SecretStore, credential_ref
from product.protocols.preparation.test_identity_preparation import IdentityPreparationRequest, IdentityPreparationResult, IdentityPreparationResultType, PreparedCookieRef
from product.protocols.web.target import WebTargetDefinition


_CREDENTIAL_SECRET_MAX_BYTES = 2_560


class IdentityPreparationBrowserAdapter:
    """根据明确登录授权保存当前目标的最小状态；普通流程有窗口，固定官方配方可无窗口。"""

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
        headless: bool = False,
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
            browser = playwright.chromium.launch(headless=headless or request.verify_only)
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
            if request.verify_only:
                self._restore_session(request,context,secret_store,bearer_tokens)
            page = context.new_page()
            origin = request.target_scope.allowed_origins[0]
            profile = request.authentication
            if request.verify_only:
                if bearer_tokens:context.set_extra_http_headers({'Authorization':'Bearer '+next(iter(bearer_tokens))})
                status,body=0,None
                try:
                    response=page.goto(origin+profile.verification.path)
                    status=response.status
                    try:body=response.json()
                    except (ValueError,PlaywrightError):pass
                except PlaywrightError:pass
                snapshot = self._verify(request,page,bearer_tokens,clock(),request.session_prepared_at_us,response={'status':status,'body':body})
                if safety_error is not None:raise safety_error
                return IdentityPreparationResult(schema_version='1',preparation_id=request.preparation_id,
                    project_id=request.project_id,identity_id=request.identity_id,
                    result_type=IdentityPreparationResultType.CHECKED,verification=snapshot)
            if profile and profile.method != 'BROWSER_SESSION':
                page.route(origin+'/__jiejian_auth_input__',lambda route:route.fulfill(status=200,content_type='text/html',body='<html lang="zh-CN"></html>'))
                page.goto(origin+'/__jiejian_auth_input__')
                self._credential_form(page,profile.method)
            else:
                page.goto(origin+(profile.login_path if profile else '/'))
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
            if profile and profile.method != 'BROWSER_SESSION':
                self._submit_credentials(request,page,context,bearer_tokens)
            prepared_at = clock()
            snapshot = self._verify(request,page,bearer_tokens,clock(),prepared_at) if profile else None
            if safety_error is not None:
                raise safety_error
            result = self._capture_login_state(
                request,
                context,
                bearer_tokens,
                secret_store,
                prepared_at_us=prepared_at,
                before_secret_write=before_secret_write,
                error_observer=error_observer,
            )
            return result.model_copy(update={'verification':snapshot}) if result.result_type is IdentityPreparationResultType.PREPARED else result
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

    @staticmethod
    def _restore_session(request,context,store,tokens):
        cookies=[]
        for cookie in request.existing_cookies:
            value=store.read(cookie.value_secret_ref)
            if value is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,'会话凭据不可用')
            item=dict(name=cookie.name,value=value,domain=cookie.domain,path=cookie.path,
                secure=cookie.secure,httpOnly=cookie.http_only,sameSite=cookie.same_site.capitalize())
            if cookie.expires_at_us is not None:
                item['expires']=cookie.expires_at_us/1_000_000
            cookies.append(item)
        if cookies:
            context.add_cookies(cookies)
        if request.existing_bearer_ref:
            token=store.read(request.existing_bearer_ref)
            if token is None:
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,'会话凭据不可用')
            tokens.add(token)

    @staticmethod
    def _credential_form(page,method):
        # 输入只存在于独立浏览器内存；控制面、进程协议及日志不接收秘密值。
        title='输入访问令牌' if method=='BEARER' else '登录应用'
        inputs='<label>访问令牌<input id="token" type="password" autocomplete="off"></label>' if method=='BEARER' else '<label>账号<input id="username" autocomplete="off"></label><label>密码<input id="password" type="password" autocomplete="off"></label>'
        page.set_content('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>'+title+'</title><style>body{font:16px system-ui;background:#eef2f7;color:#202a3b;margin:0;display:grid;place-items:center;min-height:100vh}main{background:white;border:1px solid #d7dfea;border-radius:20px;padding:40px;width:min(420px,75vw)}h1{font-size:24px}label{display:grid;gap:8px;margin:24px 0}input{font:inherit;border:1px solid #8798b1;border-radius:8px;padding:12px}p{color:#56677f;line-height:1.6}</style><main><h1>'+title+'</h1>'+inputs+'<p>填写后返回界鉴，选择“我已完成登录”。秘密只用于本次登录。</p></main></html>')

    @staticmethod
    def _submit_credentials(request,page,context,tokens):
        profile=request.authentication
        if profile.method=='BEARER':
            token=page.locator('#token').input_value()
            page.locator('#token').fill('')
            if not token or len(token.encode())>_CREDENTIAL_SECRET_MAX_BYTES or any(ord(char)<33 or ord(char)==127 for char in token):
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,'令牌为空或格式不支持')
            context.clear_cookies()
            tokens.add(token)
            return
        credentials={profile.username_field:page.locator('#username').input_value(),profile.password_field:page.locator('#password').input_value()}
        page.locator('#username').fill('')
        page.locator('#password').fill('')
        response=page.evaluate('''async ({url,credentials})=>{const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials),redirect:'error'});return {status:r.status,body:await r.json().catch(()=>null)}}''',dict(url=request.target_scope.allowed_origins[0]+profile.login_path,credentials=credentials))
        credentials.clear()
        if not 200<=response['status']<300:
            raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,'应用未接受本次登录')
        token=response['body']
        for key in profile.token_path:
            token=token.get(key) if isinstance(token,dict) else None
        if isinstance(token,str) and token:
            if len(token.encode())>_CREDENTIAL_SECRET_MAX_BYTES or any(ord(char)<33 or ord(char)==127 for char in token):
                raise JiejianError(ErrorCode.TEST_IDENTITY_NOT_READY,'登录接口返回的令牌格式不支持')
            context.clear_cookies()
            tokens.add(token)

    @staticmethod
    def _verify(request,page,tokens,checked_at,prepared_at,*,response=None):
        config=request.authentication.verification
        headers={'Authorization':'Bearer '+next(iter(tokens))} if len(tokens)==1 else {}
        if response is None:
            response=page.evaluate('''async ({url,headers})=>{try{const r=await fetch(url,{headers,redirect:'error'});return {status:r.status,body:await r.json().catch(()=>null)}}catch{return {status:0,body:null}}}''',dict(url=request.target_scope.allowed_origins[0]+config.path,headers=headers))
        status='UNAVAILABLE'
        subject=role=None
        if response['status'] in (401,403):
            status='AUTH_EXPIRED'
        elif 200<=response['status']<300:
            def field(path):
                value=response['body']
                for key in path:
                    value=value.get(key) if isinstance(value,dict) else None
                return value
            actual_subject,actual_role=field(config.subject_path),field(config.role_path)
            if actual_subject is None or actual_role is None:
                status='FIELD_MISSING'
            elif actual_subject!=config.expected_subject:
                status='SUBJECT_MISMATCH'
            elif actual_role!=config.expected_role:
                status='ROLE_MISMATCH'
            else:
                status='VERIFIED'
                subject,role=config.expected_subject,config.expected_role
        return IdentityVerificationSnapshot(status=status,checked_at_us=checked_at,
            origin=request.target_scope.allowed_origins[0],profile_fingerprint=boundary_sha256(request.authentication.model_dump(mode='json')),
            session_prepared_at_us=prepared_at,subject=subject,role=role)

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
