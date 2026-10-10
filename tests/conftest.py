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
