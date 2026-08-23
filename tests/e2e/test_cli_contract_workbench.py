from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from product.backend.cli.app import app

pytestmark = [pytest.mark.e2e, pytest.mark.database]


def _invoke(runner: CliRunner, var_dir: Path, *args: str):
    result = runner.invoke(app, ["--var-dir", str(var_dir), *args])
    assert result.exit_code == 0, result.stdout + result.stderr + (f"\n{result.exception!r}" if result.exception else "")
    return json.loads(result.stdout)


def test_cli_contract_workbench_profile_lifecycle(tmp_path: Path) -> None:
    runner = CliRunner()
    profile = Path("samples/web/fixed/profile.json").resolve()
    contract = Path("samples/web/fixed/contract.json").resolve()
    var_dir = tmp_path / "var"
    contract_v2 = tmp_path / "contract-v2.json"
    contract_payload = json.loads(contract.read_text(encoding="utf-8"))
    contract_payload["version"] = 2
    contract_v2.write_text(json.dumps(contract_payload), encoding="utf-8")
    workspace = _invoke(runner, var_dir, "contract", "workspace", str(profile))
    assert workspace["project"]["project_id"] == "permission-check-fixed"
    requirement = _invoke(
        runner,
        var_dir,
        "contract",
        "requirement-add",
        str(profile),
        "--text",
        "suggestion id=cli-requirement kind=FOREIGN_READ observations=resource_state severity=high",
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
        str(profile),
        "--requirement",
        requirement["requirement_id"],
        "--actor",
        "cli-test",
    )
    assert requirement_derived["persisted_candidates"]
    draft = _invoke(
        runner,
        var_dir,
        "contract",
        "draft",
        str(profile),
        "permission-check-contract",
        "--snapshot",
        str(contract),
        "--actor",
        "cli-test",
    )
    assert draft["status"] == "DRAFT"
    review = _invoke(runner, var_dir, "contract", "transition", str(profile), "permission-check-contract", "1", "submit", "--actor", "reviewer")
    assert review["status"] == "REVIEW"
    active = _invoke(runner, var_dir, "contract", "transition", str(profile), "permission-check-contract", "1", "activate", "--actor", "approver")
    assert active["status"] == "ACTIVE"
    assessment = _invoke(runner, var_dir, "contract", "assessment", str(profile), "permission-check-contract", "1")
    assert assessment["eligible"] is True
    drift = _invoke(runner, var_dir, "contract", "drift", str(profile), "permission-check-contract", "1")
    assert drift["contract_id"] == "permission-check-contract"
    revised = _invoke(
        runner,
        var_dir,
        "contract",
        "revise",
        str(profile),
        "permission-check-contract",
        "--snapshot",
        str(contract_v2),
        "--actor",
        "cli-test",
    )
    assert revised["version"] == 2
    diff = _invoke(
        runner,
        var_dir,
        "contract",
        "diff",
        str(profile),
        "permission-check-contract",
        "2",
        "--from-version",
        "1",
    )
    assert diff["from_version"] == 1
    assert diff["to_version"] == 2


def test_cli_contract_workbench_rejects_invalid_action(tmp_path: Path) -> None:
    runner = CliRunner()
    profile = Path("samples/web/fixed/profile.json").resolve()
    result = runner.invoke(
        app,
        ["--var-dir", str(tmp_path / "var"), "contract", "transition", str(profile), "missing", "1", "bogus"],
    )
    assert result.exit_code != 0
    assert "INPUT_INVALID" in result.stderr
