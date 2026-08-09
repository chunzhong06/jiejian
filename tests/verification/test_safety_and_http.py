from __future__ import annotations

import pytest
from pydantic import ValidationError

from jiejian.domain.verification import TargetScope
from jiejian.errors import ErrorCode, JiejianError
from jiejian.verification.http import HttpExecutor
from jiejian.verification.safety import TargetGuard


def make_scope(
    base_url: str,
    *,
    allow_private: bool = True,
    max_requests: int = 8,
    max_response_bytes: int = 1024,
) -> TargetScope:
    parsed_host_port = base_url.removeprefix("http://").split(":")
    host = parsed_host_port[0]
    port = int(parsed_host_port[1])
    return TargetScope(
        base_url=base_url,
        allowed_origins=(base_url,),
        allowed_hosts=(host,),
        allowed_ports=(port,),
        allow_private_network=allow_private,
        max_requests=max_requests,
        max_response_bytes=max_response_bytes,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": "ftp://8.8.8.8:80"},
        {"base_url": "http://user@8.8.8.8:80"},
        {"base_url": "http://8.8.8.8:81"},
        {"base_url": "http://8.8.8.8:80/path"},
    ],
)
def test_target_scope_rejects_invalid_base_boundaries(overrides: dict[str, str]) -> None:
    values = {
        "base_url": "http://8.8.8.8:80",
        "allowed_origins": ("http://8.8.8.8:80",),
        "allowed_hosts": ("8.8.8.8",),
        "allowed_ports": (80,),
    }
    values.update(overrides)
    with pytest.raises(ValidationError):
        TargetScope(**values)


def test_target_scope_requires_explicit_private_network_authorization() -> None:
    with pytest.raises(ValidationError):
        make_scope("http://127.0.0.1:8080", allow_private=False)


@pytest.mark.parametrize("host", ["example.test", "localhost", "::1"])
def test_target_scope_rejects_dns_and_ipv6_hosts(host: str) -> None:
    rendered = f"[{host}]" if ":" in host else host
    with pytest.raises(ValidationError):
        TargetScope(
            base_url=f"http://{rendered}:8080",
            allowed_origins=(f"http://{rendered}:8080",),
            allowed_hosts=(host,),
            allowed_ports=(8080,),
            allow_private_network=True,
        )


def test_guard_always_rejects_metadata_address() -> None:
    scope = make_scope("http://169.254.169.254:80", allow_private=True)
    with pytest.raises(JiejianError) as captured:
        TargetGuard(scope).authorize_path("/latest/meta-data")
    assert captured.value.code == ErrorCode.SCOPE_PRIVATE_NETWORK.value


def test_guard_rejects_userinfo_port_and_cross_origin_redirect() -> None:
    guard = TargetGuard(make_scope("http://127.0.0.1:8080"))
    with pytest.raises(JiejianError) as captured:
        guard.authorize_url("http://user@127.0.0.1:8080/resource")
    assert captured.value.code == ErrorCode.SCOPE_URL.value
    with pytest.raises(JiejianError) as captured:
        guard.authorize_url("http://127.0.0.1:8081/resource")
    assert captured.value.code == ErrorCode.SCOPE_PORT.value
    with pytest.raises(JiejianError) as captured:
        guard.authorize_redirect("http://127.0.0.1:8080/a", "http://example.com/b")
    assert captured.value.code == ErrorCode.SCOPE_REDIRECT.value


def test_executor_enforces_request_and_response_budgets(sample_server_factory) -> None:
    running = sample_server_factory()
    executor = HttpExecutor(
        TargetGuard(
            make_scope(
                f"http://127.0.0.1:{running.port}",
                max_requests=1,
                max_response_bytes=10,
            )
        )
    )
    try:
        with pytest.raises(JiejianError) as captured:
            executor.request("GET", "/health", case_id="budget-case")
        assert captured.value.code == ErrorCode.EXEC_RESPONSE_TOO_LARGE.value
        with pytest.raises(JiejianError) as captured:
            executor.request("GET", "/health", case_id="budget-case")
        assert captured.value.code == ErrorCode.EXEC_BUDGET.value
    finally:
        executor.close()
