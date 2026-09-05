# 验证录制子进程的 stdin/stdout 协议与秘密失败边界。

from __future__ import annotations
import sqlite3
from io import BytesIO, StringIO
from pathlib import Path
import pytest
from product.backend.core.lifecycle import JobState
from product.backend.core.recording import RecordingState
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols import RecordingRunnerResult, canonical_recording_json_bytes, parse_recording_result
from product.backend.workflows.recording.submission import SubmitRecording
from product.backend.infra.recording.process import execute_recording_runner
from product.backend.infra.runtime.jobs.recording import RecordingJobHandler
from product.backend.infra.artifacts.run_packages import attempt_paths_for
from tests.fixtures.recording import RecordingContext as _Context, runner_request as _request, captured_result as _captured_result
pytestmark = pytest.mark.database
NOW_US = 1_820_000_000_000_000
PROJECT_ID = "recording-project"

def test_recording_runner_uses_single_json_stdin_and_stdout() -> None:
    request = _request("rec_" + "6" * 32)
    expected = _captured_result(request.recording_id)
    stdout = BytesIO()
    stderr = StringIO()

    exit_code = execute_recording_runner(
        stdin=BytesIO(canonical_recording_json_bytes(request)),
        stdout=stdout,
        stderr=stderr,
        environ={"RECORDING_SECRET": "recording-test-secret"},
        adapter=_ControlledAdapter(expected),
    )

    assert exit_code == 0
    assert parse_recording_result(stdout.getvalue()) == expected
    assert stderr.getvalue() == ""

def test_secret_bearing_runner_result_fails_without_persisting_payload(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    sentinel = "recording-real-secret-sentinel"
    try:
        request = _request(
            "rec_" + "3" * 32,
            secret_refs=("env:RECORDING_SECRET",),
        )
        submission = context.application.submit(
            SubmitRecording(
                request=context.bind_request(request),
                flow_id="secret-rejection-flow",
                idempotency_key="recording-secret-failure",
                max_attempts=1,
                available_at_us=NOW_US + 100,
                now_us=NOW_US + 100,
                job_id="job_" + "4" * 32,
            ),
            known_secrets=(sentinel,),
        )
        times = iter((NOW_US + 110, NOW_US + 120, NOW_US + 130))
        worker = RecordingJobHandler(
            var_dir=context.var_dir,
            lease_owner="recording-worker",
            uow_factory=context.uow_factory,
            attempts=context.attempts,
            application=context.application,
            request_store=context.request_store,
            cancel_path_for=lambda root, job: attempt_paths_for(root, job).cancel_path,
            controlled_runner=lambda _request, _cancelled: _captured_result(
                request.recording_id,
                project_id=context.project_id,
                response_body=f'{{"id":"{sentinel}"}}',
            ),
            environ={"RECORDING_SECRET": sentinel},
            utc_now_us=lambda: next(times),
        )

        with pytest.raises(JiejianError) as raised:
            worker.run_job(submission.job.job_id)

        assert raised.value.code == ErrorCode.RECORD_SECRET_EXPOSED.value
        with context.uow_factory() as work:
            job = work.jobs.get(submission.job.job_id)
            recording = work.recordings.get(request.recording_id)
            drafts = work.flow_drafts.list_for_recording(request.recording_id)
        assert job is not None and job.state is JobState.FAILED
        assert recording is not None and recording.state is RecordingState.FAILED
        assert recording.browser_events == ()
        assert drafts == ()
        connection = sqlite3.connect(context.database_path)
        try:
            dump = "\n".join(connection.iterdump())
        finally:
            connection.close()
        assert sentinel not in dump
    finally:
        context.engine.dispose()

def _context(tmp_path: Path) -> _Context:
    return _Context(tmp_path)

class _ControlledAdapter:
    def __init__(self, result: RecordingRunnerResult) -> None:
        self._result = result

    def run(self, *_args: object, **_kwargs: object) -> RecordingRunnerResult:
        return self._result
