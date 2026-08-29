# 验证命令行入口中的诊断信息。

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from product.backend.cli.app import app
from product.backend.infra.runtime import diagnostics


@pytest.fixture
def trusted_doctor_environment(
    isolated_environment: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    uv = isolated_environment / "uv.exe"
    frontend = isolated_environment / "frontend-dist"
    chromium = isolated_environment / "chromium.exe"
    uv.touch()
    chromium.touch()
    frontend.mkdir()
    (frontend / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
    monkeypatch.setenv("JIEJIAN_RUNTIME_MODE", "development")
    monkeypatch.setenv("JIEJIAN_UV_VERSION", "0.11.12")
    monkeypatch.setenv("JIEJIAN_UV_EXECUTABLE", str(uv))
    monkeypatch.setenv("JIEJIAN_FRONTEND_DIST", str(frontend))
    monkeypatch.setattr(
        diagnostics,
        "python_environment_report",
        lambda: {
            "schema_version": "1",
            "ok": True,
            "runtime_mode": "development",
            "runtime_fingerprint": "test-fingerprint",
            "executable": "D:/runtime/python.exe",
            "version": "3.13.15",
            "prefix": "D:/runtime",
            "environment_type": "conda",
            "user_site_on_sys_path": False,
            "package_origins": {},
            "issues": [],
        },
    )
    monkeypatch.setattr(
        diagnostics,
        "_playwright_check",
        lambda: diagnostics.DoctorCheck(
            name="playwright",
            required=True,
            ok=True,
            message="Playwright 与 Chromium 可用",
            details={
                "package_version": "1.61.0",
                "chromium_executable": str(chromium),
            },
        ),
    )
    return isolated_environment


def test_root_help_is_task_oriented() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for text in ("status", "serve", "app", "account", "flow", "check", "result", "history", "settings", "system"):
        assert text in result.stdout
    for section in ("普通任务", "图形界面", "运行与维护"):
        assert section in result.stdout
    for removed in ("advanced", "Profile", "Baseline", "Gate", "LEGACY_PROFILE", "VarDir"):
        assert removed not in result.stdout


def test_command_groups_without_leaf_show_help_and_succeed() -> None:
    groups = (
        ("app",),
        ("account",),
        ("flow",),
        ("check",),
        ("result",),
        ("history",),
        ("settings",),
        ("system",),
        ("system", "clean"),
    )
    for group in groups:
        result = CliRunner().invoke(app, list(group))
        assert result.exit_code == 0, (group, result.stdout, result.stderr)
        assert "用法：" in result.stdout
        for framework_title in ("Usage:", "Options", "Commands", "Arguments"):
            assert framework_title not in result.stdout
        for removed in ("Profile", "Baseline", "Gate", "LEGACY_PROFILE", "VarDir"):
            assert removed not in result.stdout


def test_invalid_command_and_missing_argument_use_chinese_framework_messages() -> None:
    unknown = CliRunner().invoke(app, ["app", "unknown"])
    missing = CliRunner().invoke(app, ["app", "show"])

    assert unknown.exit_code != 0
    assert "没有名为“unknown”的命令" in unknown.output
    assert "No such command" not in unknown.output
    assert missing.exit_code != 0
    assert "缺少必需参数“project_id”" in missing.output
    assert "Missing argument" not in missing.output


def test_doctor_json_is_stable_and_requires_playwright_with_chromium(
    trusted_doctor_environment: Path,
) -> None:
    isolated_environment = trusted_doctor_environment
    runtime = isolated_environment / "runtime"
    config = isolated_environment / "doctor.toml"
    config.write_text(
        f'[jiejian]\nvar_dir = "{runtime.as_posix()}"\nlog_level = "INFO"\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--config", str(config), "--json", "system", "doctor"])

    assert result.exit_code == 0, result.stdout
    envelope = json.loads(result.stdout)
    assert envelope["schema_version"] == "1"
    assert envelope["kind"] == "system-doctor"
    report = envelope["data"]
    assert report["schema_version"] == "1"
    assert report["ok"] is True
    assert result.stderr == ""
    log_path = runtime / "logs" / "app" / "jiejian.log"
    log_payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert log_payload["component"] == "doctor"
    assert log_payload["event_code"] == "DOCTOR_COMPLETED"
    assert [check["name"] for check in report["checks"]] == [
        "python",
        "dependencies",
        "uv",
        "node",
        "pnpm",
        "frontend",
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
    assert playwright["required"] is True
    assert playwright["ok"] is True
    for name in ("node", "pnpm"):
        check = next(item for item in report["checks"] if item["name"] == name)
        assert check["ok"] is True
        assert check["required"] is False
    assert "运行阶段不需要" in check["message"]


def test_doctor_rejects_legacy_local_json_position() -> None:
    result = CliRunner().invoke(app, ["system", "doctor", "--json"])

    assert result.exit_code != 0


def test_doctor_returns_nonzero_when_a_required_check_fails(
    isolated_environment: Path,
) -> None:
    config = isolated_environment / "invalid.toml"
    config.write_text(
        '[jiejian]\nschema_version = "999"\nvar_dir = "runtime"\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--config", str(config), "--json", "system", "doctor"])

    assert result.exit_code == 1
    report = json.loads(result.stdout)["data"]
    assert report["ok"] is False
    config_check = next(
        check for check in report["checks"] if check["name"] == "config"
    )
    assert config_check["required"] is True
    assert config_check["ok"] is False


def test_doctor_uses_cli_trace_override_without_polluting_json_stdout(
    trusted_doctor_environment: Path,
) -> None:
    isolated_environment = trusted_doctor_environment
    config = isolated_environment / "doctor.toml"
    config.write_text(
        '[jiejian]\nvar_dir = "runtime"\nlog_level = "INFO"\ntrace_id = "config-trace"\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        ["--config", str(config), "--trace-id", "cli-trace", "--json", "system", "doctor"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["ok"] is True
    assert result.stderr == ""
    log_path = Path("runtime") / "logs" / "app" / "jiejian.log"
    assert json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])["trace_id"] == "cli-trace"


def test_doctor_respects_error_log_level(trusted_doctor_environment: Path) -> None:
    isolated_environment = trusted_doctor_environment
    config = isolated_environment / "doctor.toml"
    config.write_text(
        '[jiejian]\nvar_dir = "runtime"\nlog_level = "ERROR"\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["--config", str(config), "--json", "system", "doctor"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["data"]["ok"] is True
    assert result.stderr == ""


def test_doctor_human_uses_named_checks_and_conclusion(
    trusted_doctor_environment: Path,
) -> None:
    isolated_environment = trusted_doctor_environment
    config = isolated_environment / "doctor-human.toml"
    config.write_text(
        '[jiejian]\nvar_dir = "runtime"\nlog_level = "INFO"\n',
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app, ["--human", "--config", str(config), "system", "doctor"]
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    assert result.stdout.startswith("界鉴运行环境\n\n所有必要检查均已通过")
    assert "Python：" in result.stdout
    assert "Python 依赖：已准备" in result.stdout
    assert "数据库：SQLite 可用" in result.stdout
    assert "通过 ·" not in result.stdout
    assert "checks：" not in result.stdout


def test_toolchain_probe_is_local_version_check_without_network(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "project"
    package = project / "product" / "frontend"
    package.mkdir(parents=True)
    (package / "package.json").write_text(
        '{"engines":{"node":">=24.13.0 <25"},"packageManager":"pnpm@11.21.0"}',
        encoding="utf-8",
    )
    config = project / "product" / "config"
    config.mkdir()
    (config / "toolchain.json").write_text(
        json.dumps(
            {
                "node": {"development_range": ">=24.13.0 <25"},
                "pnpm": {"version": "11.21.0"},
                "uv": {"version": "0.11.12"},
            }
        ),
        encoding="utf-8",
    )
    node = tmp_path / "node.exe"
    pnpm = tmp_path / "pnpm.cmd"
    node.touch()
    pnpm.touch()
    calls = []
    monkeypatch.setattr(
        diagnostics.shutil,
        "which",
        lambda name: str(node if name == "node" else pnpm),
    )

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        version_text = "v24.13.0\n" if command[0].endswith("node.exe") else "11.21.0\n"
        return type("Completed", (), {"returncode": 0, "stdout": version_text})()

    monkeypatch.setattr(diagnostics.subprocess, "run", fake_run)
    node_check = diagnostics._local_tool_check(
        name="node", executable_name="node", required=True, project_root=project
    )
    pnpm_check = diagnostics._local_tool_check(
        name="pnpm", executable_name="pnpm", required=True, project_root=project
    )

    assert node_check.ok and pnpm_check.ok
    assert node_check.details["path"].endswith("node.exe")
    assert pnpm_check.details["version"] == "11.21.0"
    assert all(call[1]["timeout"] == 3 for call in calls)
    assert all(call[1]["cwd"] == package for call in calls)
    assert all("http" not in str(call[0]).lower() for call in calls)


def test_status_human_mode_does_not_require_an_interactive_terminal(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["--var-dir", str(tmp_path / "var"), "--human", "status"],
    )

    assert result.exit_code == 0
    assert result.stderr == ""
    assert result.stdout.startswith("界鉴工作台")
    assert "接入应用" in result.stdout


def test_maintenance_cli_uses_application_service_and_preserves_data(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    data = var_dir / "data" / "keep.txt"
    cached = var_dir / "cache" / "assistant" / "rebuild.bin"
    data.parent.mkdir(parents=True)
    cached.parent.mkdir(parents=True)
    data.write_text("keep", encoding="utf-8")
    cached.write_bytes(b"cache")

    cleaned = CliRunner().invoke(
        app, ["--var-dir", str(var_dir), "system", "clean", "assistant", "--confirm"]
    )

    assert cleaned.exit_code == 0, cleaned.stdout + cleaned.stderr
    assert data.read_text(encoding="utf-8") == "keep"
    assert not cached.exists()
