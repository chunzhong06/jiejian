from __future__ import annotations

import json
from pathlib import Path
import time

import pytest
from typer.testing import CliRunner

from jiejian.application.context import ApplicationContext
from jiejian.cli.app import app
from jiejian.execution.request_store import ExecutionRequestStore
from jiejian.execution.submission import ExecutionSubmissionService, SubmitExecutionV1

pytestmark = [pytest.mark.e2e, pytest.mark.database]


def _invoke(runner: CliRunner, var_dir: Path, *args: str):
    result = runner.invoke(app, ["--var-dir", str(var_dir), *args])
    assert result.exit_code == 0, result.stdout + (f"\n{result.exception!r}" if result.exception else "")
    return json.loads(result.stdout)


def test_cli_contract_workbench_flow_only_lifecycle(tmp_path: Path) -> None:
    runner = CliRunner()
    project = Path("samples/fixed_apps/ownership/project.yaml").resolve()
    var_dir = tmp_path / "var"
    workspace = _invoke(runner, var_dir, "contract", "workspace", str(project))
    assert workspace["project"]["project_id"] == "ownership-safe"
    requirement = _invoke(
        runner,
        var_dir,
        "contract",
        "requirement-add",
        str(project),
        "--text",
        "rule id=cli-requirement kind=foreign_read observers=http severity=high",
        "--tag",
        "pii",
        "--actor",
        "cli-test",
    )
    requirement_derived = _invoke(
        runner,
        var_dir,
        "contract",
        "derive",
        str(project),
        "--requirement",
        requirement["requirement_id"],
        "--actor",
        "cli-test",
    )
    assert requirement_derived["persisted_candidates"]
    derived = _invoke(runner, var_dir, "contract", "derive", str(project), "--include-flow", "--actor", "cli-test")
    candidates = derived["persisted_candidates"]
    assert candidates
    candidate_ids = [item["candidate_id"] for item in candidates]
    draft = _invoke(
        runner,
        var_dir,
        "contract",
        "draft",
        str(project),
        "cli-contract",
        *sum((["--candidate", item] for item in candidate_ids), []),
        "--actor",
        "cli-test",
    )
    assert draft["status"] == "DRAFT"
    review = _invoke(runner, var_dir, "contract", "transition", str(project), "cli-contract", "1", "submit", "--actor", "reviewer")
    assert review["status"] == "REVIEW"
    active = _invoke(runner, var_dir, "contract", "transition", str(project), "cli-contract", "1", "activate", "--actor", "approver")
    assert active["status"] == "ACTIVE"
    assessment = _invoke(runner, var_dir, "contract", "assessment", str(project), "cli-contract", "1")
    assert assessment["eligible"] is True
    drift = _invoke(runner, var_dir, "contract", "drift", str(project), "cli-contract", "1")
    assert drift["contract_id"] == "cli-contract"
    revised = _invoke(
        runner,
        var_dir,
        "contract",
        "revise",
        str(project),
        "cli-contract",
        *sum((["--candidate", item] for item in candidate_ids), []),
        "--actor",
        "cli-test",
    )
    assert revised["version"] == 2
    diff = _invoke(
        runner,
        var_dir,
        "contract",
        "diff",
        str(project),
        "cli-contract",
        "2",
        "--from-version",
        "1",
    )
    assert diff["from_version"] == 1
    assert diff["to_version"] == 2


def test_cli_contract_workbench_rejects_invalid_action(tmp_path: Path) -> None:
    runner = CliRunner()
    project = Path("samples/fixed_apps/ownership/project.yaml").resolve()
    result = runner.invoke(
        app,
        ["--var-dir", str(tmp_path / "var"), "contract", "transition", str(project), "missing", "1", "bogus"],
    )
    assert result.exit_code != 0
    assert "INPUT_INVALID" in result.stderr


def test_cli_contract_workbench_history_reads_execution_request(tmp_path: Path) -> None:
    runner = CliRunner()
    project = Path("samples/fixed_apps/ownership/project.yaml").resolve()
    var_dir = tmp_path / "var"
    run_id = "run_" + "a" * 32
    job_id = "job_" + "b" * 32
    context = ApplicationContext(var_dir)
    try:
        record, _ = context.projects.register(project, revalidate=True)
        request = context.execution_requests.execution_request(record.project_id)
        now_us = time.time_ns() // 1_000
        ExecutionSubmissionService(context.uow_factory, ExecutionRequestStore(var_dir)).submit(
            SubmitExecutionV1(
                request=request,
                idempotency_key="cli-history",
                available_at_us=now_us,
                now_us=now_us,
                run_id=run_id,
                job_id=job_id,
            )
        )
    finally:
        context.close()
    history = _invoke(runner, var_dir, "contract", "history", run_id)
    assert history["source"] == "EXECUTION_REQUEST"
    assert history["execution_job_id"] == job_id
