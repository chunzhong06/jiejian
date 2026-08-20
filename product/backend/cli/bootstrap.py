# CLI 运行时装配
# 为命令加载配置、迁移后存储、ApplicationCore 与已安装前端资源。

from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from collections.abc import Iterator, Mapping
from pathlib import Path

import typer

from product.backend.infra.runtime.settings import Settings, load_settings
from product.backend.infra.runtime.logging import configure_logging


@dataclass(frozen=True, slots=True)
class CliOptions:
    config: Path | None
    var_dir: Path | None
    log_level: str | None
    trace_id: str | None
    presentation: str = "auto"
    machine_only: bool = False
    verbose: bool = False


def runtime_settings(context: typer.Context) -> Settings:
    options: CliOptions = context.obj
    loaded = load_settings(
        config_path=options.config,
        cli_overrides={
            "var_dir": options.var_dir,
            "log_level": options.log_level,
            "trace_id": options.trace_id,
        },
    )
    configure_logging(
        loaded.settings.log_level,
        trace_id=loaded.settings.trace_id,
        var_dir=loaded.settings.var_dir,
        console=False,
    )
    return loaded.settings


@contextmanager
def application_scope(
    context: typer.Context, *, environ: Mapping[str, str] | None = None
) -> Iterator[object]:
    settings = runtime_settings(context)
    from product.backend.workflows.context import ApplicationCore

    application = ApplicationCore(settings.var_dir, environ=environ)
    try:
        yield application
    finally:
        application.close()


def default_frontend_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"
