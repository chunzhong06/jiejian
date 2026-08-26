# 提供运行时、Worker 与作业测试的共用夹具。

from __future__ import annotations

from collections.abc import Callable

import pytest

from product.backend.infra.runtime.jobs.requests import PersistedExecutionRequest
from tests.fixtures.runner import runner_input


@pytest.fixture
def runtime_request_factory() -> Callable[[], PersistedExecutionRequest]:
    def create() -> PersistedExecutionRequest:
        current_input = runner_input()
        return PersistedExecutionRequest(
            schema_version="1",
            budget=current_input.budget,
            project_snapshot=current_input.project_snapshot,
        )

    return create
