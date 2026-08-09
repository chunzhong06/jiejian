from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from jiejian.domain.lifecycle import RunVerdict
from jiejian.protocols import (
    RunnerInputV1,
    RunnerResultType,
    canonical_json_bytes,
    parse_runner_result,
)
from jiejian.worker.process_environment import minimal_process_environment


def _runner_input(request, *, job_suffix: str = "1") -> RunnerInputV1:
    return RunnerInputV1(
        schema_version="1",
        run_id="run_0123456789abcdef0123456789abcdef",
        job_id=f"job_{job_suffix * 32}",
        attempt=1,
        lease_owner="worker-process-test",
        fencing_token=1,
        created_at_us=1_790_000_000_000_000,
        budget=request.budget,
        project_snapshot=request.project_snapshot,
    )


def _run_subprocess(
    tmp_path: Path,
    runner_input: RunnerInputV1,
    environment: dict[str, str],
    *,
    create_staging: bool = False,
) -> tuple[subprocess.CompletedProcess[bytes], Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    input_path = tmp_path / "input.json"
    attempt_dir = tmp_path / "attempt"
    staging = attempt_dir / "staging"
    attempt_dir.mkdir(parents=True)
    input_path.write_bytes(canonical_json_bytes(runner_input))
    if create_staging:
        staging.mkdir()
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "jiejian.runner",
            "--input",
            str(input_path),
            "--staging",
            str(staging),
        ],
        cwd=tmp_path,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return completed, staging


@pytest.mark.parametrize(
    ("variant", "owner_observer", "expected"),
    [
        ("safe", True, RunVerdict.PASS),
        ("vulnerable", True, RunVerdict.BLOCK),
        ("safe", False, RunVerdict.INCONCLUSIVE),
    ],
)
def test_runner_process_executes_golden_results_and_is_the_network_pid(
    variant: str,
    owner_observer: bool,
    expected: RunVerdict,
    sample_server_factory,
    stage1_project_factory,
    stage23_request_factory,
    tmp_path: Path,
) -> None:
    server = sample_server_factory(variant, echo_identity="attacker")
    project = stage1_project_factory(server.port, owner_observer=owner_observer)
    request = stage23_request_factory(project)
    runner_input = _runner_input(request)
    environment = minimal_process_environment(
        os.environ | server.environ,
        secret_names=(
            "JIEJIAN_SAMPLE_OWNER_TOKEN",
            "JIEJIAN_SAMPLE_ATTACKER_TOKEN",
        ),
    )
    completed, staging = _run_subprocess(tmp_path, runner_input, environment)

    assert completed.returncode == 0
    assert completed.stdout == b""
    assert completed.stderr == b""
    result = parse_runner_result(
        (staging / "result.json").read_bytes(),
        known_secrets=tuple(server.tokens.values()),
    )
    assert result.result_type is RunnerResultType.SUCCESS
    assert result.verdict is expected
    assert server.server.runner_process_ids
    assert len(set(server.server.runner_process_ids)) == 1
    assert server.server.runner_process_ids[0] != os.getpid()
    persisted = b"".join(
        path.read_bytes() for path in staging.rglob("*") if path.is_file()
    )
    assert all(token.encode() not in persisted for token in server.tokens.values())


def test_runner_exit_codes_bad_input_missing_secret_cancel_and_write_failure(
    sample_server_factory,
    stage1_project_factory,
    stage23_request_factory,
    tmp_path: Path,
) -> None:
    server = sample_server_factory("safe")
    request = stage23_request_factory(stage1_project_factory(server.port))
    runner_input = _runner_input(request, job_suffix="2")
    base_environment = minimal_process_environment(os.environ)

    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    bad_input = bad_dir / "input.json"
    bad_input.write_text('{"schema_version":"2"}', encoding="utf-8")
    bad = subprocess.run(
        [sys.executable, "-B", "-m", "jiejian.runner", "--input", str(bad_input), "--staging", str(bad_dir / "staging")],
        cwd=bad_dir,
        env=base_environment,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert bad.returncode == 64
    assert not (bad_dir / "staging" / "result.json").exists()

    missing, missing_staging = _run_subprocess(
        tmp_path / "missing", runner_input, base_environment
    )
    assert missing.returncode == 0
    missing_result = parse_runner_result((missing_staging / "result.json").read_bytes())
    assert missing_result.result_type is RunnerResultType.FATAL_ERROR
    assert missing_result.error.code == "SECRET_MISSING"

    cancel_root = tmp_path / "cancel"
    cancel_root.mkdir()
    cancel_attempt = cancel_root / "attempt"
    cancel_attempt.mkdir()
    (cancel_attempt / "cancel.requested").write_text("cancel\n", encoding="utf-8")
    cancel_input = cancel_root / "input.json"
    cancel_input.write_bytes(canonical_json_bytes(runner_input))
    environment = minimal_process_environment(
        os.environ | server.environ,
        secret_names=("JIEJIAN_SAMPLE_OWNER_TOKEN", "JIEJIAN_SAMPLE_ATTACKER_TOKEN"),
    )
    cancelled = subprocess.run(
        [sys.executable, "-B", "-m", "jiejian.runner", "--input", str(cancel_input), "--staging", str(cancel_attempt / "staging")],
        cwd=cancel_root,
        env=environment,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert cancelled.returncode == 0
    cancelled_result = parse_runner_result(
        (cancel_attempt / "staging" / "result.json").read_bytes(),
        known_secrets=tuple(server.tokens.values()),
    )
    assert cancelled_result.result_type is RunnerResultType.CANCELLED

    write_failure, _ = _run_subprocess(
        tmp_path / "write-failure",
        runner_input,
        environment,
        create_staging=True,
    )
    assert write_failure.returncode == 74
