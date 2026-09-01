# 提供测试套件共用的环境隔离与基础夹具。

from __future__ import annotations

import os
from pathlib import Path
from secrets import token_urlsafe
from threading import Thread
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from tests.fixtures.web_test_target import create_web_test_target
from samples.web.collaboration_space.source.server import (
    create_collaboration_space_server,
)


@pytest.fixture
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for key in tuple(os.environ):
        if key.startswith("JIEJIAN_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def web_test_target_factory(request: pytest.FixtureRequest) -> Callable[..., Any]:
    running: list[tuple[Any, Thread]] = []

    def start(
        *,
        fail_cleanup: bool = False,
        echo_identity: str | None = None,
        request_delay_seconds: float = 0.0,
    ) -> Any:
        tokens = {
            "member": f"member-{token_urlsafe(18)}",
            "reader": f"reader-{token_urlsafe(18)}",
        }
        observer_token = f"observer-{token_urlsafe(18)}"
        passwords = {
            "member": f"web-member-{token_urlsafe(18)}",
            "reader": f"web-reader-{token_urlsafe(18)}",
        }
        sessions = {
            account: f"session-{account}-{token_urlsafe(18)}"
            for account in ("member", "reader")
        }
        server = create_web_test_target(
            tokens=tokens,
            observer_token=observer_token,
            passwords=passwords,
            sessions=sessions,
            fail_cleanup=fail_cleanup,
            echo_secret=tokens.get(echo_identity) if echo_identity else None,
            request_delay_seconds=request_delay_seconds,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        running.append((server, thread))
        return SimpleNamespace(
            server=server,
            port=server.server_port,
            tokens=tokens,
            passwords=passwords,
            environ={
                "JIEJIAN_WEB_TEST_MEMBER_TOKEN": tokens["member"],
                "JIEJIAN_WEB_TEST_READER_TOKEN": tokens["reader"],
                "JIEJIAN_WEB_TEST_OBSERVER_TOKEN": observer_token,
            },
        )

    def stop_all() -> None:
        for server, thread in running:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    request.addfinalizer(stop_all)
    return start


@pytest.fixture
def collaboration_space_factory(request: pytest.FixtureRequest, tmp_path: Path) -> Callable[..., Any]:
    """为 Sample 事实测试注入临时凭据，并在用例结束时回收本机服务与 worker。"""

    running: list[tuple[Any, Thread]] = []

    def start(
        authorization_order: str = "AUTHORIZE_BEFORE_ENQUEUE",
        blob_observation: str = "AVAILABLE",
    ) -> Any:
        policy_path = tmp_path / f"authorization-policy-{len(running)}.py"
        policy_path.write_text(
            "# 测试实例使用独立源码策略，避免并发用例改写仓库中的官方样例。\n\n"
            "def export_authorization_order():\n"
            f'    return "{authorization_order}"\n',
            encoding="utf-8",
        )
        credentials = {
            "passwords": {
                "alice": f"test-alice-{token_urlsafe(18)}",
                "bob": f"test-bob-{token_urlsafe(18)}",
            },
            "session_material": {
                account: f"session-{account}-{token_urlsafe(18)}"
                for account in ("alice", "bob")
            },
            "queue_sas": "sv=2023-11-03&se=2099-01-01T00%3A00%3A00Z&sp=r&sr=q&sig=test-queue-signature",
            "blob_sas": "sv=2023-11-03&se=2099-01-01T00%3A00%3A00Z&sp=rl&sr=c&sig=test-blob-signature",
            "task_bearer": f"task-bearer-{token_urlsafe(18)}",
            "owner_observer": f"owner-observer-{token_urlsafe(18)}",
        }
        server = create_collaboration_space_server(
            port=0,
            authorization_order=authorization_order,
            blob_observation=blob_observation,
            runtime_root=tmp_path / f"runtime-{len(running)}",
            authorization_policy_path=policy_path,
            **credentials,
        )
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        running.append((server, thread))
        return SimpleNamespace(
            server=server,
            port=server.server_port,
            base_url=f"http://127.0.0.1:{server.server_port}",
            **credentials,
        )

    def stop_all() -> None:
        for server, thread in running:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    request.addfinalizer(stop_all)
    return start
