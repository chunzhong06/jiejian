from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from jiejian.cli import app


def test_root_help_lists_doctor() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.stdout


def test_doctor_json_is_stable_and_optional_playwright_does_not_fail(
    isolated_environment: Path,
) -> None:
    runtime = isolated_environment / "runtime"
    config = isolated_environment / "doctor.toml"
    config.write_text(
        f'[jiejian]\nvar_dir = "{runtime.as_posix()}"\nlog_level = "INFO"\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--config", str(config), "doctor", "--json"])

    assert result.exit_code == 0, result.stdout
    report = json.loads(result.stdout)
    assert report["schema_version"] == "1"
    assert report["ok"] is True
    log_payload = json.loads(result.stderr)
    assert log_payload["component"] == "doctor"
    assert log_payload["event_code"] == "DOCTOR_COMPLETED"
    assert [check["name"] for check in report["checks"]] == [
        "python",
        "dependencies",
        "config",
        "var_dir",
        "sqlite",
        "playwright",
        "loopback",
        "redaction",
    ]
    assert all(check["ok"] for check in report["checks"] if check["required"])
    playwright = next(
        check for check in report["checks"] if check["name"] == "playwright"
    )
    assert playwright["required"] is False


def test_doctor_returns_nonzero_when_a_required_check_fails(
    isolated_environment: Path,
) -> None:
    config = isolated_environment / "invalid.toml"
    config.write_text(
        '[jiejian]\nschema_version = "999"\nvar_dir = "runtime"\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--config", str(config), "doctor", "--json"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["ok"] is False
    config_check = next(
        check for check in report["checks"] if check["name"] == "config"
    )
    assert config_check["required"] is True
    assert config_check["ok"] is False


def test_doctor_uses_cli_trace_override_without_polluting_json_stdout(
    isolated_environment: Path,
) -> None:
    config = isolated_environment / "doctor.toml"
    config.write_text(
        '[jiejian]\nvar_dir = "runtime"\nlog_level = "INFO"\ntrace_id = "config-trace"\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["--config", str(config), "--trace-id", "cli-trace", "doctor", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"] is True
    assert json.loads(result.stderr)["trace_id"] == "cli-trace"


def test_doctor_respects_error_log_level(isolated_environment: Path) -> None:
    config = isolated_environment / "doctor.toml"
    config.write_text(
        '[jiejian]\nvar_dir = "runtime"\nlog_level = "ERROR"\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--config", str(config), "doctor", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["ok"] is True
    assert result.stderr == ""
