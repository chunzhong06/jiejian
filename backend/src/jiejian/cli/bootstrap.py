# =============================================================================
# CLI 运行时装配
#
# 定位
#   CLI 命令与配置、数据库、ApplicationContext 和前端资源之间的共享边界
#
# 职责
#   加载确定性配置｜打开迁移后的存储｜定位已安装前端资源
#
# 调用链
#   cli.commands.* → cli.bootstrap → Runtime / Storage / ApplicationContext
# =============================================================================

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path

import typer

from ..runtime.config import Settings, load_settings
from ..runtime.logging import configure_logging
from ..storage import (
    StorageUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
    default_database_path,
    upgrade_database,
)


@dataclass(frozen=True, slots=True)
class CliOptions:
    config: Path | None
    var_dir: Path | None
    log_level: str | None
    trace_id: str | None


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
    )
    return loaded.settings


def open_storage(
    settings: Settings,
) -> tuple[object, partial[StorageUnitOfWork]]:
    var_dir = settings.var_dir.resolve()
    database_path = default_database_path(var_dir)
    upgrade_database(database_path)
    engine = create_sqlite_engine(database_path)
    factory = partial(StorageUnitOfWork, create_session_factory(engine))
    return engine, factory


def default_frontend_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "frontend" / "dist"
