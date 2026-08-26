# 验证进程运行时中的运行配置。

from __future__ import annotations

from pathlib import Path

import product.backend.infra.runtime.settings as config_module
from product.backend.infra.runtime.settings import Settings, load_settings


def test_built_in_defaults_are_generated_from_settings(
    isolated_environment: Path, monkeypatch
) -> None:
    monkeypatch.setattr(config_module, "default_config_path", lambda: None)

    loaded = load_settings(environ={})

    assert loaded.settings == Settings()
    assert loaded.sources == {
        "schema_version": "built-in",
        "var_dir": "built-in",
        "log_level": "built-in",
        "trace_id": "built-in",
    }


def test_configuration_source_precedence(
    isolated_environment: Path, monkeypatch
) -> None:
    default_file = isolated_environment / "default.toml"
    default_file.write_text(
        """[jiejian]\nvar_dir = "from-default"\nlog_level = "WARNING"\ntrace_id = "default"\n""",
        encoding="utf-8",
    )
    explicit_file = isolated_environment / "explicit.toml"
    explicit_file.write_text(
        """[jiejian]\nvar_dir = "from-explicit"\nlog_level = "ERROR"\ntrace_id = "explicit"\n""",
        encoding="utf-8",
    )
    monkeypatch.setenv("JIEJIAN_VAR_DIR", "from-environment")
    monkeypatch.setenv("JIEJIAN_LOG_LEVEL", "DEBUG")

    loaded = load_settings(
        default_path=default_file,
        config_path=explicit_file,
        cli_overrides={"var_dir": Path("from-cli")},
    )

    assert loaded.settings.var_dir == Path("from-cli")
    assert loaded.settings.log_level == "DEBUG"
    assert loaded.settings.trace_id == "explicit"
    assert loaded.settings.schema_version == "1"
    assert loaded.sources == {
        "schema_version": "built-in",
        "var_dir": "cli",
        "log_level": "environment",
        "trace_id": "explicit-config",
    }


def test_environment_values_are_validated(isolated_environment: Path, monkeypatch) -> None:
    default_file = isolated_environment / "default.toml"
    default_file.write_text("[jiejian]\n", encoding="utf-8")
    monkeypatch.setenv("JIEJIAN_LOG_LEVEL", "warning")

    loaded = load_settings(default_path=default_file)

    assert loaded.settings.log_level == "WARNING"
