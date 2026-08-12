# =============================================================================
# 运行配置加载
#
# 定位
#   默认值、配置文件、环境变量与 CLI 覆盖之间的确定性合并边界
#
# 职责
#   校验 Settings｜记录每项来源｜拒绝无效运行时配置
#
# 调用链
#   CLI / API bootstrap → load_settings → Settings / LoadedSettings
# =============================================================================

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from ..errors import ErrorCode, JiejianError

_ENVIRONMENT_KEYS = {
    "JIEJIAN_SCHEMA_VERSION": "schema_version",
    "JIEJIAN_VAR_DIR": "var_dir",
    "JIEJIAN_LOG_LEVEL": "log_level",
    "JIEJIAN_TRACE_ID": "trace_id",
}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1"
    var_dir: Path = Path("var")
    log_level: str = "INFO"
    trace_id: str | None = None

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != "1":
            raise ValueError("unsupported configuration schema version")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return normalized


@dataclass(frozen=True, slots=True)
class LoadedSettings:
    settings: Settings
    sources: Mapping[str, str]


def default_config_path() -> Path | None:
    """查找工作目录或源码树中的阶段 0 默认配置。"""

    candidates = (
        Path.cwd() / "config" / "default.toml",
        Path(__file__).resolve().parents[3] / "config" / "default.toml",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _read_config(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise JiejianError(
            ErrorCode.CFG_FILE,
            f"无法读取{label}",
            details={"reason": type(exc).__name__},
        ) from exc

    section = document.get("jiejian", document)
    if not isinstance(section, dict):
        raise JiejianError(ErrorCode.CFG_INVALID, f"{label}中的 jiejian 必须是表")
    return section


def _apply(
    merged: dict[str, Any],
    sources: dict[str, str],
    values: Mapping[str, Any],
    source: str,
) -> None:
    for key, value in values.items():
        if value is not None:
            merged[key] = value
            sources[key] = source


def load_settings(
    *,
    config_path: Path | None = None,
    cli_overrides: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    default_path: Path | None = None,
) -> LoadedSettings:
    """按内置、默认文件、显式文件、环境变量、CLI 的顺序加载配置。"""

    merged: dict[str, Any] = Settings().model_dump()
    sources = {key: "built-in" for key in merged}

    selected_default = default_path if default_path is not None else default_config_path()
    if selected_default is not None:
        _apply(
            merged,
            sources,
            _read_config(selected_default, "默认配置文件"),
            "default.toml",
        )

    if config_path is not None:
        _apply(
            merged,
            sources,
            _read_config(config_path, "显式配置文件"),
            "explicit-config",
        )

    environment = os.environ if environ is None else environ
    environment_values = {
        setting: environment[variable]
        for variable, setting in _ENVIRONMENT_KEYS.items()
        if variable in environment
    }
    _apply(merged, sources, environment_values, "environment")
    _apply(merged, sources, cli_overrides or {}, "cli")

    try:
        settings = Settings.model_validate(merged)
    except ValidationError as exc:
        issues = [
            {
                "location": ".".join(str(part) for part in issue["loc"]),
                "type": issue["type"],
            }
            for issue in exc.errors()
        ]
        raise JiejianError(
            ErrorCode.CFG_INVALID,
            "配置校验失败",
            details={"issues": issues},
        ) from exc

    return LoadedSettings(settings=settings, sources=dict(sources))
