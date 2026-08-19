from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

from product.backend.api.routers.jobs import build_jobs_router
from product.backend.core.lifecycle import JobState


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
