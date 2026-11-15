"""逻辑域名、解析边界与实际固定连接独立核对，不访问公网。"""
import socket
import httpx
import pytest
from product.protocols.web.target import WebTargetScope
from product.protocols.web.identity import AuthTargetScope
from product.backend.infrastructure.execution.web.adapter import WebTargetGuard
from product.backend.infrastructure.execution.web.pinned_transport import PinnedLoopbackTransport
from product.backend.domain.errors import JiejianError


def scope(**kwargs):
    return WebTargetScope(base_url='http://localhost:8100',allowed_origins=('http://localhost:8100',),
        allowed_hosts=('localhost',),allowed_ports=(8100,),allow_private_network=True,**kwargs)


def resolution(monkeypatch, *addresses):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *args,**kwargs:[(socket.AF_INET,socket.SOCK_STREAM,0,'',(value,8100)) for value in addresses])


def test_domain_scope_is_explicit_for_business_and_authentication():
    declared=scope()
    assert declared.base_url=='http://localhost:8100'
    assert AuthTargetScope.model_validate_json(declared.model_dump_json()).allowed_hosts==('localhost',)


@pytest.mark.parametrize('addresses',[('192.0.2.1',),('127.0.0.1','192.0.2.1'),('::1',),()])
def test_domain_cannot_resolve_outside_the_declared_ipv4_loopback(monkeypatch,addresses):
    resolution(monkeypatch,*addresses)
    with pytest.raises(JiejianError):WebTargetGuard(scope()).authorize_path('/me')


def test_resolution_drift_redirect_and_self_alias_are_rejected(monkeypatch):
    resolution(monkeypatch,'127.0.0.1')
    guard=WebTargetGuard(scope())
    assert guard.authorize_path('/me').addresses==('127.0.0.1',)
    resolution(monkeypatch,'127.0.0.1','::1')
    with pytest.raises(JiejianError,match='解析已变化'):guard.authorize_path('/me')
    with pytest.raises(JiejianError):guard.authorize_redirect('http://localhost:8100/a','http://127.0.0.1:8101/private')
    with pytest.raises(JiejianError):WebTargetGuard(scope(),reserved_origins=('http://127.0.0.1:8100',)).authorize_path('/')


def test_pinned_connection_preserves_cookie_domain_and_tls_hostname():
    calls=[]
    def respond(request):
        calls.append(request)
        assert request.url.host=='127.0.0.1'
        assert request.headers['host']=='localhost:8100'
        assert request.extensions['sni_hostname']=='localhost'
        return httpx.Response(200,headers={'Set-Cookie':'session=private-fixture; Path=/; HttpOnly'},json={'ok':True})
    with httpx.Client(transport=PinnedLoopbackTransport(transport=httpx.MockTransport(respond)),trust_env=False) as client:
        result=client.get('https://localhost:8100/me',extensions={'jiejian_authorized_address':'127.0.0.1'})
        assert result.request.url.host=='localhost'
        client.get('https://localhost:8100/me',extensions={'jiejian_authorized_address':'127.0.0.1'})
        assert calls[1].headers['cookie']=='session=private-fixture'
        with pytest.raises(JiejianError):client.get('https://localhost:8100/me')


def test_resolution_timeout_never_reaches_the_transport(monkeypatch):
    from threading import Event
    from product.backend.infrastructure.execution.web.adapter import HttpExecutionAdapter
    from product.backend.domain.errors import ErrorCode
    release = Event()
    def stalled(*args, **kwargs):
        release.wait(2)
        return [(socket.AF_INET,socket.SOCK_STREAM,0,'',('127.0.0.1',8100))]
    monkeypatch.setattr(socket, 'getaddrinfo', stalled)
    adapter = HttpExecutionAdapter(scope(timeout_seconds=0.02))
    def forbidden(*args, **kwargs):
        pytest.fail('解析超时不得进入 HTTP 传输')
    monkeypatch.setattr(adapter.client, 'stream', forbidden)
    try:
        with pytest.raises(JiejianError) as captured:
            adapter.request('GET', '/me', case_id='dns-timeout')
        assert captured.value.code == ErrorCode.EXEC_TIMEOUT.value
        assert adapter.requests_used == 0
    finally:
        release.set()
        adapter.close()


def test_authentication_scope_cannot_bypass_self_target_alias(monkeypatch):
    from product.backend.infrastructure.execution.web.adapter import HttpExecutionAdapter
    from product.backend.domain.errors import ErrorCode
    adapter = HttpExecutionAdapter(scope(),reserved_origins=('http://127.0.0.1:8100',))
    try:
        with pytest.raises(JiejianError) as captured:
            adapter.request('GET','/session',case_id='auth-self',auth_scope=AuthTargetScope.model_validate_json(scope().model_dump_json()))
        assert captured.value.code == ErrorCode.SELF_TARGET_FORBIDDEN.value
        assert adapter.auth_requests_used == {}
    finally:
        adapter.close()


def test_authentication_requests_keep_the_same_resolution_baseline(monkeypatch):
    from product.backend.infrastructure.execution.web.adapter import HttpExecutionAdapter
    resolution(monkeypatch,'127.0.0.1')
    adapter = HttpExecutionAdapter(scope())
    adapter.client.close()
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(200,json={'ok':True})
    adapter.client = httpx.Client(transport=httpx.MockTransport(respond))
    authentication = AuthTargetScope.model_validate_json(scope().model_dump_json())
    try:
        adapter.request('GET','/session',case_id='auth-drift',auth_scope=authentication)
        resolution(monkeypatch,'127.0.0.1','::1')
        with pytest.raises(JiejianError,match='解析已变化'):
            adapter.request('GET','/session',case_id='auth-drift',auth_scope=authentication)
        assert len(calls) == 1
    finally:
        adapter.close()


@pytest.mark.level4
def test_untrusted_localhost_certificate_stops_before_any_http_request(tmp_path):
    """临时自签名证书只属于本用例，不修改系统信任库或产品TLS设置。"""
    import ssl
    from datetime import datetime, timedelta, timezone
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from product.backend.infrastructure.execution.web.adapter import HttpExecutionAdapter
    from product.backend.domain.errors import ErrorCode
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
        .not_valid_after(now+timedelta(hours=1)).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]),critical=False)
        .sign(key,hashes.SHA256()))
    cert_path, key_path = tmp_path/'certificate.pem', tmp_path/'key.pem'
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    received = []
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(self.path)
            self.send_response(200);self.end_headers()
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert_path,key_path)
    server.socket = tls.wrap_socket(server.socket,server_side=True)
    thread = Thread(target=server.serve_forever,daemon=True);thread.start()
    origin = f'https://localhost:{server.server_port}'
    adapter = HttpExecutionAdapter(WebTargetScope(base_url=origin,allowed_origins=(origin,),
        allowed_hosts=('localhost',),allowed_ports=(server.server_port,),allow_private_network=True))
    try:
        with pytest.raises(JiejianError) as captured:
            adapter.request('GET','/private',case_id='untrusted-tls')
        assert captured.value.code == ErrorCode.TARGET_UNREACHABLE.value
        assert received == []
    finally:
        adapter.close();server.shutdown();server.server_close();thread.join(5)
        assert not thread.is_alive()
