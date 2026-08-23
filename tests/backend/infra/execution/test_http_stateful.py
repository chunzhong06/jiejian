from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs

from product.backend.core.verification.facts import ExecutionOutcome
from product.backend.infra.execution.web.adapter import HttpExecutionAdapter, HttpResponse, extract_response_value
from product.backend.infra.execution.web.identity import HttpIdentityRuntime
from product.protocols import (
    AuthTargetScope,
    CookieSessionIdentityBinding,
    FormUrlEncodedBody,
    HttpOutcomeClassifier,
    HttpParameter,
    HttpPredicate,
    HttpPredicateKind,
    HttpRequestTemplate,
    HttpIdentityKind,
    LoginWorkflowIdentityBinding,
    MultipartBody,
    MultipartPart,
    OAuth2ClientCredentialsIdentityBinding,
    OAuth2RefreshTokenIdentityBinding,
    ResponseExtractor,
    ResponseExtractorKind,
    ValueSlot,
    ValueSlotConsumer,
    ValueSlotSource,
    WebTargetDefinition,
    WebTargetScope,
)


class _StatefulHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    token_number = 0

    def log_message(self, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        self.server.request_paths.append(self.path)  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/login":
            self._send(200, {"ok": True, "csrf": "csrf-local"}, headers={"Set-Cookie": "sid=session-local; Path=/"})
            return
        if self.path == "/oauth/token":
            form = parse_qs(body.decode("utf-8"))
            if form.get("grant_type") == ["refresh_token"]:
                _StatefulHandler.token_number += 1
            token = f"access-{_StatefulHandler.token_number}"
            self._send(200, {"access_token": token})
            return
        if self.path == "/submit":
            cookie_ok = "sid=session-local" in self.headers.get("Cookie", "")
            csrf_ok = self.headers.get("X-CSRF") == "csrf-local"
            if not cookie_ok or not csrf_ok:
                self._send(200, {"success": False, "code": "FORBIDDEN"})
            else:
                self._send(200, {"success": True, "code": "OK", "content_type": self.headers.get("Content-Type", "")})
            return
        if self.path == "/echo-cookie":
            self._send(200, {"cookie": self.headers.get("Cookie", "")})
            return
        if self.path == "/oauth-business":
            self._send(200 if self.headers.get("Authorization", "").startswith("Bearer access-") else 403, {"ok": True})
            return
        self._send(404, {})

    def _send(self, status: int, payload: dict[str, object], *, headers: dict[str, str] | None = None) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def _server() -> tuple[ThreadingHTTPServer, Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StatefulHandler)
    server.request_paths = []  # type: ignore[attr-defined]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _target(port: int) -> WebTargetDefinition:
    origin = f"http://127.0.0.1:{port}"
    return WebTargetDefinition(
        scope=WebTargetScope(
            base_url=origin,
            allowed_origins=(origin,),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(port,),
            allow_private_network=True,
            max_requests=32,
        ),
        reset_path="/reset",
    )


def test_real_cookie_csrf_form_multipart_and_identity_isolation() -> None:
    server, thread = _server()
    adapter = HttpExecutionAdapter(_target(server.server_port), fixture_artifacts={"fixture-avatar": b"fixture-data"})
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        binding = CookieSessionIdentityBinding(kind=HttpIdentityKind.COOKIE_SESSION, bootstrap_template_ids=("login",), csrf_slot_id="csrf")
        runtime = HttpIdentityRuntime(binding, resolve_secret=lambda _ref: None, business_origin=origin)
        login = HttpRequestTemplate(
            method="POST",
            path="/login",
            body=FormUrlEncodedBody(fields=(HttpParameter(name="user", literal="operator"),)),
        )

        def send_bootstrap(request: HttpRequestTemplate, *, bootstrap: bool = False):
            assert bootstrap is True
            return adapter.request(
                request.method,
                request.path,
                case_id="case-cookie",
                body=request.body,
                headers=request.headers,
                identity_runtime=runtime,
                bootstrap_request=True,
            )

        runtime.bootstrap(send_bootstrap, requests=(login,))
        assert runtime.cookies.get("sid") == "session-local"
        echoed = adapter.request(
            "POST",
            "/echo-cookie",
            case_id="case-cookie",
            identity_runtime=runtime,
        )
        assert "session-local" not in json.dumps(echoed.data)
        runtime.set_csrf("csrf", "csrf-local", origin=origin, max_length=64)
        csrf_slot = ValueSlot(
            slot_id="csrf",
            source=ValueSlotSource.PRIOR_STEP_HEADER,
            consumer=ValueSlotConsumer.HEADER,
            max_length=64,
            secret=True,
            source_path="X-CSRF",
            producer_step=1,
            consumer_step=2,
        )
        classifier = HttpOutcomeClassifier(
            accepted=(HttpPredicate(kind=HttpPredicateKind.JSON_PATH_EQUALS, json_path="$.success", expected=True),),
            denied=(HttpPredicate(kind=HttpPredicateKind.JSON_PATH_EQUALS, json_path="$.code", expected="FORBIDDEN"),),
        )
        form_template = HttpRequestTemplate(
            method="POST",
            path="/submit",
            headers=(HttpParameter(name="X-CSRF", slot_id="csrf"),),
            body=FormUrlEncodedBody(fields=(HttpParameter(name="value", literal="form-value"),)),
            input_slots=(csrf_slot,),
        )
        fact = adapter.execute(form_template, case_id="case-cookie", action_id="submit", classifier=classifier, slot_values={"csrf": runtime.slot_value("csrf")}, identity_runtime=runtime)
        assert fact.outcome is ExecutionOutcome.ACCEPTED

        multipart_template = HttpRequestTemplate(
            method="POST",
            path="/submit",
            headers=(HttpParameter(name="X-CSRF", slot_id="csrf"),),
            body=MultipartBody(parts=(MultipartPart(name="file", fixture_artifact_id="fixture-avatar", filename="avatar.txt"),)),
            input_slots=(csrf_slot,),
        )
        multipart_fact = adapter.execute(multipart_template, case_id="case-cookie", action_id="upload", classifier=classifier, slot_values={"csrf": "csrf-local"}, identity_runtime=runtime)
        assert multipart_fact.outcome is ExecutionOutcome.ACCEPTED

        isolated = HttpIdentityRuntime(binding, resolve_secret=lambda _ref: None, business_origin=origin)
        denied_fact = adapter.execute(form_template, case_id="case-isolated", action_id="submit", classifier=classifier, slot_values={"csrf": "csrf-local"}, identity_runtime=isolated)
        assert denied_fact.outcome is ExecutionOutcome.FAILED
        isolated.close()
        runtime.close()
    finally:
        adapter.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_header_cookie_and_html_csrf_extractors_execute_the_bounded_sources() -> None:
    response = HttpResponse(
        status_code=200,
        data={},
        headers={
            "x-csrf-token": "header-token",
            "set-cookie": "csrf_cookie=cookie-token; Path=/; HttpOnly",
        },
        body=(
            b'<form><input type="hidden" name="csrf" value="hidden-token"></form>'
            b'<meta name="csrf" content="meta-token">'
            b'<div id="state">ready</div>'
        ),
    )
    json_response = HttpResponse(
        status_code=200,
        data={},
        body=b'{"items":[{"token":"array-token"}]}',
    )

    assert extract_response_value(json_response, ResponseExtractor(extractor_id="array-csrf", kind=ResponseExtractorKind.JSON_PATH, json_path="$.items[0].token", secret=True)) == "array-token"
    assert extract_response_value(response, ResponseExtractor(extractor_id="header-csrf", kind=ResponseExtractorKind.HEADER, header_name="X-CSRF-Token", secret=True)) == "header-token"
    assert extract_response_value(response, ResponseExtractor(extractor_id="cookie-csrf", kind=ResponseExtractorKind.COOKIE, cookie_name="csrf_cookie", secret=True)) == "cookie-token"
    assert extract_response_value(response, ResponseExtractor(extractor_id="hidden-csrf", kind=ResponseExtractorKind.HTML_ATTRIBUTE, selector="input[name]", attribute="value", secret=True)) == "hidden-token"
    assert extract_response_value(response, ResponseExtractor(extractor_id="meta-csrf", kind=ResponseExtractorKind.HTML_ATTRIBUTE, selector="meta[name]", attribute="content", secret=True)) == "meta-token"
    assert extract_response_value(response, ResponseExtractor(extractor_id="state-text", kind=ResponseExtractorKind.HTML_SELECTOR, selector="div#state")) == "ready"


def test_real_login_workflow_bootstrap_establishes_an_isolated_session() -> None:
    server, thread = _server()
    adapter = HttpExecutionAdapter(_target(server.server_port))
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        runtime = HttpIdentityRuntime(
            LoginWorkflowIdentityBinding(workflow_id="login-flow", csrf_slot_id="csrf"),
            resolve_secret=lambda _ref: None,
            business_origin=origin,
        )
        login = HttpRequestTemplate(method="POST", path="/login")

        def send_bootstrap(request: HttpRequestTemplate, *, bootstrap: bool = False):
            assert bootstrap is True
            return adapter.request(
                request.method,
                request.path,
                case_id="case-login-workflow",
                identity_runtime=runtime,
                bootstrap_request=True,
            )

        runtime.bootstrap(send_bootstrap, requests=(login,))

        assert runtime.bootstrapped is True
        assert runtime.cookies.get("sid") == "session-local"
        assert server.request_paths == ["/login"]  # type: ignore[attr-defined]
        runtime.close()
    finally:
        adapter.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_oauth_refresh_is_explicit_and_at_most_once() -> None:
    server, thread = _server()
    adapter = HttpExecutionAdapter(_target(server.server_port))
    try:
        origin = f"http://127.0.0.1:{server.server_port}"
        scope = AuthTargetScope(
            base_url=origin,
            allowed_origins=(origin,),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(server.server_port,),
            allow_private_network=True,
        )
        binding = OAuth2RefreshTokenIdentityBinding(
            token_path="/oauth/token",
            client_id_ref="env:CLIENT_ID",
            refresh_token_ref="env:REFRESH_TOKEN",
            auth_scope=scope,
        )
        runtime = HttpIdentityRuntime(binding, resolve_secret=lambda ref: {"env:CLIENT_ID": "client", "env:REFRESH_TOKEN": "refresh"}.get(ref), business_origin=origin)

        def send_auth(path: str, *, method: str = "POST", data=None, auth: bool = False, auth_scope=None):
            assert auth is True
            assert auth_scope is scope
            return adapter.request(method, path, case_id="oauth", data=data, identity_runtime=runtime, bootstrap_request=True, auth_scope=auth_scope)

        runtime.bootstrap(send_auth)
        assert runtime.bootstrapped is True
        assert runtime.refresh_once(send_auth, token_expired=False) is False
        assert runtime.refresh_once(send_auth, token_expired=True) is True
        assert runtime.refresh_once(send_auth, token_expired=True) is False
        assert runtime.refresh_count == 1
        business = HttpRequestTemplate(method="POST", path="/oauth-business")
        fact = adapter.execute(
            business,
            case_id="oauth",
            action_id="business",
            classifier=HttpOutcomeClassifier(accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(200,)),)),
            identity_runtime=runtime,
        )
        assert fact.outcome is ExecutionOutcome.ACCEPTED
        runtime.close()
    finally:
        adapter.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_oauth_client_credentials_bootstrap_uses_secret_refs() -> None:
    business_server, business_thread = _server()
    auth_server, auth_thread = _server()
    adapter = HttpExecutionAdapter(_target(business_server.server_port))
    try:
        origin = f"http://127.0.0.1:{business_server.server_port}"
        auth_origin = f"http://127.0.0.1:{auth_server.server_port}"
        scope = AuthTargetScope(
            base_url=auth_origin,
            allowed_origins=(auth_origin,),
            allowed_hosts=("127.0.0.1",),
            allowed_ports=(auth_server.server_port,),
            allow_private_network=True,
        )
        binding = OAuth2ClientCredentialsIdentityBinding(
            token_path="/oauth/token",
            client_id_ref="env:CLIENT_ID",
            client_secret_ref="env:CLIENT_SECRET",
            auth_scope=scope,
        )
        secrets = {"env:CLIENT_ID": "client", "env:CLIENT_SECRET": "client-secret"}
        runtime = HttpIdentityRuntime(binding, resolve_secret=secrets.get, business_origin=origin)

        def send_auth(path: str, *, method: str = "POST", data=None, auth: bool = False, auth_scope=None):
            assert auth is True
            assert auth_scope is scope
            return adapter.request(method, path, case_id="oauth-client", data=data, identity_runtime=runtime, bootstrap_request=True, auth_scope=auth_scope)

        runtime.bootstrap(send_auth)
        assert "/oauth/token" in auth_server.request_paths  # type: ignore[attr-defined]
        assert "/oauth/token" not in business_server.request_paths  # type: ignore[attr-defined]
        fact = adapter.execute(
            HttpRequestTemplate(method="POST", path="/oauth-business"),
            case_id="oauth-client",
            action_id="business",
            classifier=HttpOutcomeClassifier(accepted=(HttpPredicate(kind=HttpPredicateKind.STATUS_IN, statuses=(200,)),)),
            identity_runtime=runtime,
        )
        assert fact.outcome is ExecutionOutcome.ACCEPTED
        assert "client-secret" in runtime.redaction_secrets()
        runtime.close()
    finally:
        adapter.close()
        for server, thread in ((business_server, business_thread), (auth_server, auth_thread)):
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
