from __future__ import annotations

from collections.abc import Callable

import pytest

from product.backend.infra.runtime.job_requests import PersistedExecutionRequest
from tests.fixtures.runner import runner_input


@pytest.fixture
def runtime_request_factory() -> Callable[[], PersistedExecutionRequest]:
    def create() -> PersistedExecutionRequest:
        current_input = runner_input()
        return PersistedExecutionRequest(
            schema_version="4",
            budget=current_input.budget,
            project_snapshot=current_input.project_snapshot,
        )

    return create
