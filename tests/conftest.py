from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from secrets import token_urlsafe
from threading import Thread
from types import SimpleNamespace
from typing import Any, Callable

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "backend" / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from jiejian.sample_app import create_sample_server
from jiejian.protocols import ExecutionBudgetV1, ExecutionProjectSnapshotV1
from jiejian.verification.inputs import load_project_bundle
from jiejian.execution.request_store import PersistedExecutionRequestV1


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
        variant: str = "safe",
        *,
        fail_cleanup: bool = False,
        echo_identity: str | None = None,
        request_delay_seconds: float = 0.0,
    ) -> Any:
        tokens = {
            "owner": f"owner-{token_urlsafe(18)}",
            "attacker": f"attacker-{token_urlsafe(18)}",
        }
        server = create_sample_server(
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
                "JIEJIAN_SAMPLE_OWNER_TOKEN": tokens["owner"],
                "JIEJIAN_SAMPLE_ATTACKER_TOKEN": tokens["attacker"],
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
def stage1_project_factory(tmp_path: Path) -> Callable[..., Path]:
    created = 0

    def create(
        port: int,
        *,
        owner_observer: bool = True,
        max_requests: int = 64,
        max_response_bytes: int = 262_144,
    ) -> Path:
        nonlocal created
        created += 1
        target = tmp_path / f"project-{created}"
        shutil.copytree(PROJECT_ROOT / "samples" / "fixed_apps" / "ownership", target)
        project_path = target / "project.yaml"
        document = yaml.safe_load(project_path.read_text(encoding="utf-8"))
        document["project"]["id"] = f"test-project-{created}"
        document["target"]["base_url"] = f"http://127.0.0.1:{port}"
        document["target"]["allowed_origins"] = [f"http://127.0.0.1:{port}"]
        document["target"]["allowed_ports"] = [port]
        document["target"]["max_requests"] = max_requests
        document["target"]["max_response_bytes"] = max_response_bytes
        document["observers"]["owner_api"] = owner_observer
        project_path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return project_path

    return create


@pytest.fixture
def stage23_request_factory() -> Callable[[Path], PersistedExecutionRequestV1]:
    def create(project_path: Path) -> PersistedExecutionRequestV1:
        bundle = load_project_bundle(project_path)
        project = bundle.project
        return PersistedExecutionRequestV1(
            schema_version="1",
            budget=ExecutionBudgetV1(
                schema_version="1",
                max_requests=project.target.max_requests,
                request_timeout_us=int(project.target.timeout_seconds * 1_000_000),
                max_duration_us=60_000_000,
                max_response_bytes=project.target.max_response_bytes,
                max_parallel_cases=1,
            ),
            project_snapshot=ExecutionProjectSnapshotV1(
                schema_version="1",
                project_id=project.id,
                project_name=project.name,
                target=project.target,
                identities=project.identities,
                resources=project.resources,
                flow=bundle.flow,
                contract=bundle.contract,
                owner_observer_enabled=project.owner_observer_enabled,
                mutation_seed=project.mutation_seed,
            ),
        )

    return create
