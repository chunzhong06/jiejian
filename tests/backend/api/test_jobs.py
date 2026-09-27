# 验证后端 API中的作业接口。

from __future__ import annotations

import asyncio
import inspect
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import pytest

from product.backend.api.routers.jobs import build_jobs_router
from product.backend.core.lifecycle import JobState
from product.backend.infra.runtime.paths import RuntimePaths
from product.backend.infra.runtime.runner.progress import RunnerProgressReader, RunnerProgressWriter


@pytest.mark.parametrize('after, header, expected', [(None, '0', [1, 2]), (None, '1', [2]), (1, '0', [2])])
def test_independent_event_route_resumes_by_sequence_without_replaying(after, header, expected):
    """验证未挂载的独立 SSE reader；不将它声明为当前产品 API。"""
    events = [SimpleNamespace(sequence=number, event_type='JOB_CANCELLED', source_state=JobState.PENDING,
        target_state=JobState.CANCELLED, occurred_at_us=number, metadata={}) for number in (1, 2)]
    work = SimpleNamespace(jobs=SimpleNamespace(get=lambda _: SimpleNamespace(state=JobState.CANCELLED)),
        job_events=SimpleNamespace(list_for_job=lambda _: events))

    @contextmanager
    def unit_of_work():
        yield work

    async def connected():
        return False

    endpoint = next(route.endpoint for route in build_jobs_router(SimpleNamespace(uow_factory=unit_of_work)).routes
        if route.path == '/api/jobs/{job_id}/events')

    async def read():
        response = await endpoint('job-test', SimpleNamespace(is_disconnected=connected), after=after, last_event_id=header)
        return [chunk async for chunk in response.body_iterator]

    chunks = asyncio.run(read())
    assert [int(chunk.splitlines()[0].removeprefix('id: ')) for chunk in chunks] == expected


def test_job_events_stops_before_next_poll_when_client_disconnects() -> None:
    class Request:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls >= 2

    class Uow:
        def __init__(self) -> None:
            self.job_reads = 0

        def __enter__(self) -> Uow:
            return self

        def __exit__(self, *_args) -> None:
            return None

        @property
        def jobs(self):
            return self

        @property
        def job_events(self):
            return self

        def get(self, _job_id: str):
            self.job_reads += 1
            return SimpleNamespace(state=JobState.RUNNING)

        def list_for_job(self, _job_id: str):
            return ()

    uow = Uow()

    class Context:
        @contextmanager
        def uow_factory(self):
            yield uow

    endpoint = next(
        route.endpoint
        for route in build_jobs_router(Context()).routes
        if route.path == "/api/jobs/{job_id}/events"
    )

    async def exercise() -> None:
        response = await endpoint("job_1", Request(), after=0, last_event_id=None)
        chunks = [chunk async for chunk in response.body_iterator]
        assert chunks == []

    asyncio.run(exercise())
    assert uow.job_reads == 2


def test_job_progress_reads_only_current_attempt_and_fails_closed(tmp_path: Path) -> None:
    job = SimpleNamespace(
        job_id="job_" + "a" * 32,
        attempt=1,
        fencing_token=1,
    )
    attempt_dir = RuntimePaths(tmp_path).jobs / job.job_id / "attempts" / "1-1"
    attempt_dir.mkdir(parents=True)
    writer = RunnerProgressWriter(attempt_dir / "progress.jsonl")
    assert writer.record(
        case_id="case-" + "b" * 32,
        action_id="modify",
        twin_role=None,
        phase="PREPARE",
        state="STARTED",
        recorded_at_us=1,
    )
    writer.close()

    class Uow:
        def __enter__(self) -> Uow:
            return self

        def __exit__(self, *_args) -> None:
            return None

        @property
        def jobs(self):
            return self

        def get(self, _job_id: str):
            return job

    class Context:
        runner_progress_reader = RunnerProgressReader(tmp_path)

        @contextmanager
        def uow_factory(self):
            yield Uow()

    endpoint = next(
        route.endpoint
        for route in build_jobs_router(Context()).routes
        if route.path == "/api/jobs/{job_id}/progress"
    )

    response = asyncio.run(endpoint(job.job_id))
    payload = json.loads(response.body)
    assert tuple(inspect.signature(endpoint).parameters) == ("job_id",)
    assert payload["schema_version"] == "1"
    assert payload["data"]["attempt"] == 1
    assert payload["data"]["events"][0]["phase"] == "PREPARE"

    (attempt_dir / "progress.jsonl").write_text(
        (attempt_dir / "progress.jsonl").read_text(encoding="utf-8")[:-1],
        encoding="utf-8",
    )
    response = asyncio.run(endpoint(job.job_id))
    assert json.loads(response.body)["data"]["events"] == []

    (attempt_dir / "progress.jsonl").write_text(
        '{"schema_version":"1","sequence":2,"case_id":"case-'
        + "b" * 32
        + '","action_id":"modify","twin_role":null,"phase":"PREPARE","state":"STARTED","recorded_at_us":1}\n',
        encoding="utf-8",
    )
    response = asyncio.run(endpoint(job.job_id))
    assert json.loads(response.body)["data"]["events"] == []

    (attempt_dir / "progress.jsonl").write_bytes(b"x" * (64 * 1024 + 1))
    response = asyncio.run(endpoint(job.job_id))
    assert json.loads(response.body)["data"]["events"] == []

    old_attempt = RuntimePaths(tmp_path).jobs / job.job_id / "attempts" / "0-0"
    old_attempt.mkdir(parents=True)
    (old_attempt / "progress.jsonl").write_text(
        '{"schema_version":"1","sequence":1,"case_id":"case-'
        + "c" * 32
        + '","action_id":"delete","twin_role":null,"phase":"TARGET","state":"STARTED","recorded_at_us":1}\n',
        encoding="utf-8",
    )
    response = asyncio.run(endpoint(job.job_id))
    assert json.loads(response.body)["data"]["events"] == []
