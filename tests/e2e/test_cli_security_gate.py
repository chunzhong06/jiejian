from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from jiejian.cli.app import app
from jiejian.domain.lifecycle import CaseVerdict, RunVerdict
from jiejian.errors import ErrorCode, JiejianError
from jiejian.verification.artifacts import load_report
from jiejian.verification.models import RunResult
from jiejian.execution.dispatch import WorkerDispatcher

pytestmark = [pytest.mark.e2e, pytest.mark.database, pytest.mark.process, pytest.mark.slow]


def _run_via_cli(
    runner: CliRunner,
    var_dir: Path,
    project_path: Path,
    environment: dict[str, str],
) -> RunResult:
    result = runner.invoke(
        app,
        [
            "--var-dir",
            str(var_dir),
            "run",
            str(project_path),
            "--contract",
            str(project_path.parent / "contract.yaml"),
        ],
        env=environment,
    )
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    return RunResult.model_validate(json.loads(result.stdout))


def test_safe_and_vulnerable_golden_paths(
    sample_server_factory,
    stage1_project_factory,
    tmp_path: Path,
) -> None:
    safe_server = sample_server_factory("safe", echo_identity="attacker")
    safe_project = stage1_project_factory(safe_server.port)
    safe_result = _run_via_cli(
        CliRunner(), tmp_path / "safe-var", safe_project, safe_server.environ
    )
    assert safe_result.verdict is RunVerdict.PASS
    assert all(item.verdict is CaseVerdict.SAFE for item in safe_result.evidence)
    assert safe_server.server.runner_process_ids
    assert set(safe_server.server.runner_process_ids) != {os.getpid()}

    vulnerable_server = sample_server_factory("vulnerable")
    vulnerable_project = stage1_project_factory(vulnerable_server.port)
    vulnerable_result = _run_via_cli(
        CliRunner(),
        tmp_path / "vulnerable-var",
        vulnerable_project,
        vulnerable_server.environ,
    )
    assert vulnerable_result.verdict is RunVerdict.BLOCK
    assert vulnerable_server.server.runner_process_ids
    assert set(vulnerable_server.server.runner_process_ids) != {os.getpid()}
    side_effect = next(
        item
        for item in vulnerable_result.evidence
        if "UNAUTHORIZED_SIDE_EFFECT" in item.reason_codes
    )
    mutation_http = next(
        item
        for item in side_effect.observations
        if item.observer == "http" and item.phase == "mutation"
    )
    before = next(item for item in side_effect.observations if item.phase == "before")
    after = next(item for item in side_effect.observations if item.phase == "after")
    assert mutation_http.status_code == 403
    assert before.data != after.data


def test_missing_observer_and_cleanup_failure_are_inconclusive(
    sample_server_factory,
    stage1_project_factory,
    tmp_path: Path,
) -> None:
    normal_server = sample_server_factory("safe")
    no_observer_project = stage1_project_factory(
        normal_server.port,
        owner_observer=False,
    )
    missing = _run_via_cli(
        CliRunner(),
        tmp_path / "no-observer-var",
        no_observer_project,
        normal_server.environ,
    )
    assert missing.verdict is RunVerdict.INCONCLUSIVE
    assert "REQUIRED_OBSERVER_MISSING" in missing.reason_codes
    assert normal_server.server.runner_process_ids
    assert set(normal_server.server.runner_process_ids) != {os.getpid()}

    broken_server = sample_server_factory("safe", fail_cleanup=True)
    broken_project = stage1_project_factory(broken_server.port)
    cleanup = _run_via_cli(
        CliRunner(),
        tmp_path / "cleanup-var",
        broken_project,
        broken_server.environ,
    )
    assert cleanup.verdict is RunVerdict.INCONCLUSIVE
    assert cleanup.reason_codes == ("CLEANUP_FAILED",)
    assert len(cleanup.evidence) == 1
    assert broken_server.server.runner_process_ids
    assert set(broken_server.server.runner_process_ids) != {os.getpid()}


def test_seed_evidence_reports_and_secrets_are_stable(
    sample_server_factory,
    stage1_project_factory,
    tmp_path: Path,
) -> None:
    running = sample_server_factory("safe", echo_identity="attacker")
    project = stage1_project_factory(running.port)
    var_dir = tmp_path / "artifacts"
    runner = CliRunner()
    first = _run_via_cli(runner, var_dir, project, running.environ)
    second = _run_via_cli(runner, var_dir, project, running.environ)
    assert [item.fingerprint for item in first.evidence] == [
        item.fingerprint for item in second.evidence
    ]
    assert all(item.run_id == first.run_id for item in first.evidence)
    assert all(item.run_id == second.run_id for item in second.evidence)
    report = load_report(var_dir, first.run_id)
    assert report["run_id"] == first.run_id
    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in var_dir.rglob("*.json")
    )
    assert running.tokens["owner"] not in persisted
    assert running.tokens["attacker"] not in persisted
    assert "prefix::[REDACTED]::suffix" in persisted
    assert not list(var_dir.rglob("*.tmp-*"))
    report_path = Path(first.artifact_dir) / "artifacts" / "report" / "report.json"
    report_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(JiejianError) as captured:
        load_report(var_dir, first.run_id)
    assert captured.value.code == ErrorCode.REPORT_NOT_FOUND.value


def test_all_stage1_cli_commands_and_ci_exit_codes(
    sample_server_factory,
    stage1_project_factory,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    safe_server = sample_server_factory("safe", echo_identity="attacker")
    safe_project = stage1_project_factory(safe_server.port)
    safe_var = tmp_path / "cli-safe"
    environment = safe_server.environ

    project_validation = runner.invoke(app, ["project", "validate", str(safe_project)])
    assert project_validation.exit_code == 0
    assert json.loads(project_validation.stdout)["valid"] is True
    assert project_validation.stderr == ""

    contract_path = safe_project.parent / "contract.yaml"
    contract_validation = runner.invoke(
        app,
        ["contract", "validate", str(contract_path)],
    )
    assert contract_validation.exit_code == 0
    assert json.loads(contract_validation.stdout)["kind"] == "contract"

    run_result = runner.invoke(
        app,
        [
            "--var-dir",
            str(safe_var),
            "run",
            str(safe_project),
            "--contract",
            str(contract_path),
        ],
        env=environment,
    )
    assert run_result.exit_code == 0, run_result.output
    run_payload = json.loads(run_result.stdout)
    assert run_payload["verdict"] == "PASS"
    assert safe_server.tokens["attacker"] not in run_result.stdout
    assert "[REDACTED]" in run_result.stdout
    assert run_result.stderr == ""
    assert safe_server.server.runner_process_ids
    assert set(safe_server.server.runner_process_ids) != {os.getpid()}
    assert Path(run_payload["artifact_dir"]).is_dir()

    published_report = runner.invoke(
        app,
        ["--var-dir", str(safe_var), "report", run_payload["run_id"], "--format", "json"],
    )
    assert published_report.exit_code == 0
    assert json.loads(published_report.stdout)["run_id"] == run_payload["run_id"]

    stable = _run_via_cli(runner, safe_var, safe_project, environment)
    report_result = runner.invoke(
        app,
        ["--var-dir", str(safe_var), "report", stable.run_id, "--format", "json"],
    )
    assert report_result.exit_code == 0
    assert json.loads(report_result.stdout)["run_id"] == stable.run_id

    safe_ci = runner.invoke(
        app,
        ["--var-dir", str(tmp_path / "ci-pass"), "ci", str(safe_project)],
        env=environment,
    )
    assert safe_ci.exit_code == 0
    assert json.loads(safe_ci.stdout)["verdict"] == "PASS"

    vulnerable_server = sample_server_factory("vulnerable")
    vulnerable_project = stage1_project_factory(vulnerable_server.port)
    block_ci = runner.invoke(
        app,
        ["--var-dir", str(tmp_path / "ci-block"), "ci", str(vulnerable_project)],
        env=vulnerable_server.environ,
    )
    assert block_ci.exit_code == 1
    assert json.loads(block_ci.stdout)["verdict"] == "BLOCK"

    no_observer_project = stage1_project_factory(
        safe_server.port,
        owner_observer=False,
    )
    inconclusive_ci = runner.invoke(
        app,
        ["--var-dir", str(tmp_path / "ci-inconclusive"), "ci", str(no_observer_project)],
        env=environment,
    )
    assert inconclusive_ci.exit_code == 2
    assert json.loads(inconclusive_ci.stdout)["verdict"] == "INCONCLUSIVE"
    assert inconclusive_ci.stderr == ""


def test_cli_reads_and_rejects_tampered_legacy_report(tmp_path: Path) -> None:
    run_id = "run_" + "a" * 32
    run_dir = tmp_path / "projects" / "legacy-project" / "runs" / run_id
    report_path = run_dir / "report" / "report.json"
    report = {
        "schema_version": "1",
        "run_id": run_id,
        "project_id": "legacy-project",
        "engine_version": "0.1.0",
        "verdict": "PASS",
        "reason_codes": [],
        "evidence": [],
    }
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1",
        "run_id": run_id,
        "project_id": "legacy-project",
        "verdict": "PASS",
        "artifact_hashes": {
            "report/report.json": hashlib.sha256(report_path.read_bytes()).hexdigest()
        },
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    assert load_report(tmp_path, run_id)["run_id"] == run_id
    cli_result = CliRunner().invoke(
        app, ["--var-dir", str(tmp_path), "report", run_id]
    )
    assert cli_result.exit_code == 0
    assert json.loads(cli_result.stdout)["run_id"] == run_id

    report_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(JiejianError) as captured:
        load_report(tmp_path, run_id)
    assert captured.value.code == ErrorCode.REPORT_NOT_FOUND.value


def test_cli_uses_separate_input_system_and_safety_exit_codes(
    sample_server_factory,
    stage1_project_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CliRunner()
    running = sample_server_factory("safe")
    project = stage1_project_factory(running.port)

    missing_secret = runner.invoke(
        app,
        ["--var-dir", str(tmp_path / "missing-secret"), "ci", str(project)],
        env={
            "JIEJIAN_SAMPLE_OWNER_TOKEN": "",
            "JIEJIAN_SAMPLE_ATTACKER_TOKEN": "",
        },
    )
    assert missing_secret.exit_code == 3
    assert json.loads(missing_secret.stderr)["error"]["code"] == "SECRET_MISSING"

    unsafe_document = yaml.safe_load(project.read_text(encoding="utf-8"))
    unsafe_document["target"].update(
        {
            "base_url": "http://169.254.169.254:80",
            "allowed_origins": ["http://169.254.169.254:80"],
            "allowed_hosts": ["169.254.169.254"],
            "allowed_ports": [80],
        }
    )
    project.write_text(yaml.safe_dump(unsafe_document), encoding="utf-8")
    safety_stop = runner.invoke(
        app,
        ["--var-dir", str(tmp_path / "safety-stop"), "ci", str(project)],
        env=running.environ,
    )
    assert safety_stop.exit_code == 5
    assert json.loads(safety_stop.stderr)["error"]["code"] == "SCOPE_PRIVATE_NETWORK"

    def fail_worker(*args, **kwargs):
        raise JiejianError(ErrorCode.EXEC_REQUEST, "目标执行失败")

    monkeypatch.setattr(WorkerDispatcher, "start", fail_worker)
    system_error = runner.invoke(
        app,
        ["--var-dir", str(tmp_path / "system"), "ci", str(project)],
        env=running.environ,
    )
    assert system_error.exit_code == 4
    assert json.loads(system_error.stderr)["error"]["code"] == "EXEC_REQUEST"
