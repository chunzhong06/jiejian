# 验证本地 endpoint 候选来源、loopback 限制、排序和探测预算。

from __future__ import annotations

import http.client
import json
import socket
from pathlib import Path

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.workflows.application_understanding.endpoints import (
    EndpointDiscoveryLimits,
    EndpointProbeObservation,
    TargetEndpointDiscovery,
    normalize_loopback_endpoint,
)


def _probe_for(*reachable: str, calls: list[str] | None = None):
    allowed = set(reachable)

    def probe(endpoint: str, limits: EndpointDiscoveryLimits) -> EndpointProbeObservation:
        if calls is not None:
            calls.append(endpoint)
        return EndpointProbeObservation(
            reachable=endpoint in allowed,
            status_code=200 if endpoint in allowed else None,
            detail="测试服务已响应" if endpoint in allowed else "测试服务未响应",
        )

    return probe


def test_explicit_config_openapi_startup_and_framework_defaults_are_ranked(
    tmp_path: Path,
) -> None:
    (tmp_path / "vite.config.ts").write_text(
        "export default { server: { port: 4311 } }",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite --port 6111"}}),
        encoding="utf-8",
    )
    (tmp_path / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "servers": [{"url": "http://127.0.0.1:5222"}],
            }
        ),
        encoding="utf-8",
    )
    reachable = "http://127.0.0.1:4311"
    result = TargetEndpointDiscovery(probe=_probe_for(reachable)).discover(tmp_path)

    by_endpoint = {item.endpoint: item for item in result.candidates}
    assert by_endpoint[reachable].source_type == "CONFIG"
    assert by_endpoint["http://127.0.0.1:5222"].source_type == "OPENAPI"
    assert by_endpoint["http://127.0.0.1:6111"].source_type == "STARTUP"
    assert by_endpoint["http://127.0.0.1:5173"].source_type == "FRAMEWORK_DEFAULT"
    assert [item.rank for item in result.candidates] == sorted(
        item.rank for item in result.candidates
    )
    assert result.default_endpoint == reachable


def test_recognized_django_uses_only_its_fixed_default_port(tmp_path: Path) -> None:
    (tmp_path / "manage.py").write_text("print('not executed')", encoding="utf-8")
    calls: list[str] = []
    result = TargetEndpointDiscovery(
        probe=_probe_for("http://127.0.0.1:8000", calls=calls)
    ).discover(tmp_path)

    assert [item.endpoint for item in result.candidates] == [
        "http://127.0.0.1:8000"
    ]
    assert calls == ["http://127.0.0.1:8000"]
    assert result.default_endpoint == "http://127.0.0.1:8000"


def test_multiple_reachable_or_no_candidate_requires_explicit_user_choice(
    tmp_path: Path,
) -> None:
    servers = ["http://127.0.0.1:4101", "http://127.0.0.1:4102"]
    (tmp_path / "openapi.json").write_text(
        json.dumps({"openapi": "3.1.0", "servers": [{"url": item} for item in servers]}),
        encoding="utf-8",
    )
    multiple = TargetEndpointDiscovery(probe=_probe_for(*servers)).discover(tmp_path)
    assert multiple.default_endpoint is None
    assert multiple.manual_entry_required is False

    empty = tmp_path / "empty"
    empty.mkdir()
    none = TargetEndpointDiscovery(probe=_probe_for()).discover(empty)
    assert none.candidates == ()
    assert none.manual_entry_required is True
    assert none.request_count == 0


def test_non_loopback_and_unspecified_bind_addresses_are_never_candidates(
    tmp_path: Path,
) -> None:
    (tmp_path / "openapi.json").write_text(
        json.dumps(
            {
                "openapi": "3.1.0",
                "servers": [
                    {"url": "http://0.0.0.0:5000"},
                    {"url": "http://192.168.1.20:5001"},
                    {"url": "https://example.com"},
                ],
            }
        ),
        encoding="utf-8",
    )
    result = TargetEndpointDiscovery(probe=_probe_for()).discover(tmp_path)
    assert result.candidates == ()
    for endpoint in (
        "http://0.0.0.0:5000",
        "http://192.168.1.20:5001",
        "https://example.com",
        "http://[::1]:5002",
    ):
        with pytest.raises(JiejianError) as error:
            normalize_loopback_endpoint(endpoint)
        assert error.value.code == ErrorCode.APPLICATION_ENDPOINT_INVALID.value


def test_localhost_requires_and_normalizes_ipv4_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::1", 5173, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 5173)),
        ],
    )
    assert normalize_loopback_endpoint("http://localhost:5173/app/") == (
        "http://127.0.0.1:5173/app"
    )

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("::1", 5173, 0, 0))
        ],
    )
    with pytest.raises(JiejianError, match="仅支持 IPv4 loopback"):
        normalize_loopback_endpoint("http://localhost:5173")


def test_probe_request_count_never_exceeds_budget_or_scans_other_ports(
    tmp_path: Path,
) -> None:
    explicit = [f"http://127.0.0.1:{port}" for port in range(4200, 4210)]
    (tmp_path / "openapi.json").write_text(
        json.dumps({"openapi": "3.1.0", "servers": [{"url": item} for item in explicit]}),
        encoding="utf-8",
    )
    calls: list[str] = []
    result = TargetEndpointDiscovery(
        limits=EndpointDiscoveryLimits(max_requests=3),
        probe=_probe_for(calls=calls),
    ).discover(tmp_path)

    assert result.request_count == 3
    assert len(calls) == 3
    assert set(calls).issubset(set(explicit))
    assert all(item.endpoint in explicit for item in result.candidates)
    assert any(item.probe_detail == "未探测：已达到请求预算" for item in result.candidates)


def test_default_probe_enforces_timeout_body_budget_and_external_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class Response:
        status = 302

        def read(self, amount: int) -> bytes:
            observed["read"] = amount
            return b"x" * amount

        @staticmethod
        def getheader(name: str) -> str | None:
            return "https://example.com/outside" if name == "Location" else None

    class Connection:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            observed.update(host=host, port=port, timeout=timeout)

        def request(self, method: str, path: str, headers: dict[str, str]) -> None:
            observed.update(method=method, path=path, headers=headers)

        @staticmethod
        def getresponse() -> Response:
            return Response()

        @staticmethod
        def close() -> None:
            return None

    monkeypatch.setattr(http.client, "HTTPConnection", Connection)
    limits = EndpointDiscoveryLimits(timeout_seconds=0.25, max_response_bytes=512)
    result = TargetEndpointDiscovery._request_endpoint(
        "http://127.0.0.1:4555",
        limits,
    )

    assert observed["timeout"] == 0.25
    assert observed["read"] == 512
    assert observed["method"] == "GET"
    assert result.reachable is False
    assert result.detail == "重定向离开 loopback，已拒绝"
