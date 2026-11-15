"""固定已授权的本机连接地址，保留逻辑域名、Cookie jar 与 TLS 主机名。"""
import httpx
from product.backend.domain.errors import ErrorCode, JiejianError


class PinnedLoopbackTransport(httpx.BaseTransport):
    def __init__(self, *, transport=None):
        self._transport = transport or httpx.HTTPTransport(trust_env=False)

    def handle_request(self, request):
        if request.url.host != 'localhost':
            return self._transport.handle_request(request)
        if request.extensions.get('jiejian_authorized_address') != '127.0.0.1':
            raise JiejianError(ErrorCode.SCOPE_HOST, '域名请求缺少本次运行的地址核验')
        # Client 仍持有原 Request，故 Set-Cookie 及响应 URL 按原域名处理。
        # 内层连接使用字面量，DNS 在校验后漂移也不会改变本次实际连接。
        headers = httpx.Headers(request.headers)
        headers['Host'] = 'localhost:' + str(request.url.port or (443 if request.url.scheme == 'https' else 80))
        pinned = httpx.Request(request.method, request.url.copy_with(host='127.0.0.1'),
            headers=headers, stream=request.stream,
            extensions=dict(request.extensions, sni_hostname='localhost'))
        return self._transport.handle_request(pinned)

    def close(self):
        self._transport.close()
