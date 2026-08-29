# 提供运行时、Worker 与作业测试的共用夹具。

from __future__ import annotations

from collections.abc import Callable

import pytest

from product.backend.infra.runtime.jobs.requests import PersistedExecutionRequest
from product.protocols.execution_request import build_permission_policy_snapshot
from tests.fixtures.runner import runner_input


@pytest.fixture
def runtime_request_factory() -> Callable[[], PersistedExecutionRequest]:
    def create() -> PersistedExecutionRequest:
        current_input = runner_input()
        return PersistedExecutionRequest(
            schema_version="1",
            budget=current_input.budget,
            permission_policy=build_permission_policy_snapshot(
                current_input.project_snapshot.project_id,
                0,
                (),
            ),
            project_snapshot=current_input.project_snapshot,
        )

    return create
