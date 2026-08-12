from __future__ import annotations

import os
import subprocess
import sys
from functools import partial
from pathlib import Path

from jiejian.domain.lifecycle import RunVerdict
from jiejian.storage import (
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
)
from jiejian.execution.dispatch import WorkerDispatcher
from jiejian.execution.process_environment import minimal_process_environment

import pytest

pytestmark = [pytest.mark.database, pytest.mark.process, pytest.mark.slow]


def test_submission_process_can_exit_before_worker_and_runner_finish(
    sample_server_factory,
    stage1_project_factory,
    tmp_path: Path,
) -> None:
    server = sample_server_factory("safe", request_delay_seconds=0.05)
    project = stage1_project_factory(server.port)
    var_dir = tmp_path / "var"
    submitter = tmp_path / "submitter.py"
    submitter.write_text(
        """
from functools import partial
from pathlib import Path
from jiejian.cli.commands.runs import _persisted_request
from jiejian.storage import StorageUnitOfWork, create_session_factory, create_sqlite_engine, default_database_path, upgrade_database
from jiejian.verification.inputs import load_project_bundle
from jiejian.execution.request_store import ExecutionRequestStore, required_secret_names
from jiejian.execution.submission import ExecutionSubmissionService, SubmitExecutionV1
from jiejian.execution.dispatch import WorkerDispatcher

project = Path(__import__('sys').argv[1])
var_dir = Path(__import__('sys').argv[2])
request = _persisted_request(load_project_bundle(project))
now_us = __import__('time').time_ns() // 1000
upgrade_database(default_database_path(var_dir))
engine = create_sqlite_engine(default_database_path(var_dir))
factory = create_session_factory(engine)
uow = partial(StorageUnitOfWork, factory)
submission = ExecutionSubmissionService(uow, ExecutionRequestStore(var_dir)).submit(
    SubmitExecutionV1(
        request=request,
        idempotency_key='detached-submitter',
        max_attempts=1,
        available_at_us=now_us,
        now_us=now_us,
        run_id='run_66666666666666666666666666666666',
        job_id='job_66666666666666666666666666666666',
    ),
    known_secrets=tuple(__import__('os').environ[name] for name in required_secret_names(request)),
)
WorkerDispatcher(var_dir=var_dir, uow_factory=uow).start(
    job_id=submission.job.job_id,
    lease_owner='worker-detached-submitter',
    secret_names=required_secret_names(request),
)
print(submission.job.job_id, flush=True)
engine.dispose()
""".strip(),
        encoding="utf-8",
    )
    environment = minimal_process_environment(
        os.environ | server.environ,
        secret_names=(
            "JIEJIAN_SAMPLE_OWNER_TOKEN",
            "JIEJIAN_SAMPLE_ATTACKER_TOKEN",
        ),
    )
    submitted = subprocess.run(
        [sys.executable, "-B", str(submitter), str(project), str(var_dir)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert submitted.returncode == 0, submitted.stderr
    job_id = submitted.stdout.strip()
    assert job_id == "job_66666666666666666666666666666666"

    engine = create_sqlite_engine(default_database_path(var_dir))
    try:
        factory = create_session_factory(engine)
        dispatcher = WorkerDispatcher(
            var_dir=var_dir,
            uow_factory=partial(StorageUnitOfWork, factory),
            environ=os.environ | server.environ,
        )
        staged = dispatcher.wait(
            job_id,
            None,
            known_secrets=tuple(server.tokens.values()),
            timeout_seconds=30,
        )
        assert staged.result.verdict is RunVerdict.PASS
        assert server.server.runner_process_ids
        assert server.server.runner_process_ids[0] != os.getpid()
    finally:
        engine.dispose()
