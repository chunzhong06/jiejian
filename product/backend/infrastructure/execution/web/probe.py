"""无凭据的本机接入探测：只接受响应状态和有限前缀，不产生检查事实。"""
import time
import httpx
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.execution.web.adapter import WebTargetGuard
from product.backend.infrastructure.execution.web.pinned_transport import PinnedLoopbackTransport
from product.protocols.web.target import WebTargetScope


def probe_endpoint(scope: WebTargetScope, path: str) -> int:
    """最多一次 GET；大页面只读取前缀，不把截断正文作为完整证明返回。"""
    deadline = time.monotonic() + scope.timeout_seconds
    guard = WebTargetGuard(scope)
    target = guard.authorize_path(path)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise JiejianError(ErrorCode.EXEC_TIMEOUT, '接入探测已超过等待预算')
    try:
        with httpx.Client(transport=PinnedLoopbackTransport(), trust_env=False,
                          follow_redirects=False, timeout=remaining) as client:
            with client.stream('GET', target.url,
                headers={'Accept': 'text/html,application/json', 'User-Agent': 'Jiejian-Endpoint-Discovery'},
                extensions={'jiejian_authorized_address': target.addresses[0]}) as response:
                if 300 <= response.status_code < 400 and response.headers.get('location'):
                    guard.authorize_redirect(target.url, response.headers['location'])
                used = 0
                for chunk in response.iter_raw(chunk_size=min(1024, scope.max_response_bytes)):
                    used += len(chunk)
                    if time.monotonic() >= deadline:
                        raise JiejianError(ErrorCode.EXEC_TIMEOUT, '接入探测已超过等待预算')
                    if used >= scope.max_response_bytes:
                        break
                return response.status_code
    except httpx.TimeoutException:
        raise JiejianError(ErrorCode.EXEC_TIMEOUT, '接入探测超时') from None
    except httpx.HTTPError:
        raise JiejianError(ErrorCode.TARGET_UNREACHABLE, '接入探测无法取得响应') from None
