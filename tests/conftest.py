from __future__ import annotations

import os
from pathlib import Path
from secrets import token_urlsafe
from threading import Thread
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from product.backend.workflows.onboarding.demo_target import create_demo_target_server
from product.protocols import ExecutionBudget, ExecutionProjectSnapshot
from product.backend.infra.runtime.job_requests import PersistedExecutionRequest


@pytest.fixture
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for key in tuple(os.environ):
        if key.startswith("JIEJIAN_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def sample_server_factory(request: pytest.FixtureRequest) -> Callable[..., Any]:
    running: list[tuple[Any, Thread]] = []

    def start(
        variant: str = "fixed",
        *,
        fail_cleanup: bool = False,
        echo_identity: str | None = None,
        request_delay_seconds: float = 0.0,
    ) -> Any:
        tokens = {
            "owner": f"owner-{token_urlsafe(18)}",
            "attacker": f"attacker-{token_urlsafe(18)}",
            "peer": f"peer-{token_urlsafe(18)}",
        }
        server = create_demo_target_server(
            variant=variant,
            tokens=tokens,
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
            environ={
                "JIEJIAN_AUTHORIZATION_OWNER_TOKEN": tokens["owner"],
                "JIEJIAN_AUTHORIZATION_ATTACKER_TOKEN": tokens["attacker"],
                "JIEJIAN_AUTHORIZATION_PEER_TOKEN": tokens["peer"],
                "JIEJIAN_AUTHORIZATION_OWNER_OBSERVER": tokens["owner"],
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
def stage23_request_factory() -> Callable[[], PersistedExecutionRequest]:
    def create() -> PersistedExecutionRequest:
        from tests.execution.protocol.test_runner import _input

        runner_input = _input()
        return PersistedExecutionRequest(
            schema_version="2",
            budget=runner_input.budget,
            project_snapshot=runner_input.project_snapshot,
        )

    return create
