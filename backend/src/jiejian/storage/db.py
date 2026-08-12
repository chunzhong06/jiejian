# =============================================================================
# 数据库运行时与迁移入口
#
# 定位
#   SQLite 连接语义、SQLAlchemy Session 与 Alembic 资源之间的基础设施边界
#
# 职责
#   配置连接约束｜创建 Session factory｜定位并执行完整 migration 链
#
# 调用链
#   Application bootstrap → storage.db → SQLite / Alembic resources
# =============================================================================

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from ..errors import ErrorCode, JiejianError

SQLITE_BUSY_TIMEOUT_MS = 5_000


def default_database_path(var_dir: Path) -> Path:
    """返回配置运行目录下的默认数据库路径。"""

    return var_dir / "jiejian.db"


def configure_sqlite_engine(engine: Engine) -> None:
    """为引擎创建的每个 SQLite 连接安装安全 PRAGMA。"""

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(
        connection: sqlite3.Connection,
        _: object,
    ) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def create_sqlite_engine(database_path: Path) -> Engine:
    """创建只面向文件数据库的 SQLAlchemy 引擎。"""

    try:
        path = database_path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            f"sqlite+pysqlite:///{path.as_posix()}",
            future=True,
            poolclass=NullPool,
        )
        configure_sqlite_engine(engine)
        return engine
    except (OSError, SQLAlchemyError):
        raise JiejianError(ErrorCode.STORAGE_FAILURE, "数据库初始化失败") from None


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
        autobegin=False,
    )


@contextmanager
def _migration_resource_root() -> Iterator[Path]:
    """提供源码或已安装包中的成对 Alembic 资源目录。"""

    packaged_root = files("jiejian").joinpath("resources")
    packaged_config = packaged_root.joinpath("alembic.ini")
    packaged_migrations = packaged_root.joinpath("migrations")
    packaged_config_exists = packaged_config.is_file()
    packaged_migrations_exists = packaged_migrations.is_dir()
    if packaged_config_exists or packaged_migrations_exists:
        if not (packaged_config_exists and packaged_migrations_exists):
            raise FileNotFoundError("packaged Alembic resources are incomplete")
        with as_file(packaged_root) as extracted_root:
            yield extracted_root
        return

    source_root = Path(__file__).resolve().parents[3]
    if not (source_root / "alembic.ini").is_file() or not (
        source_root / "migrations"
    ).is_dir():
        raise FileNotFoundError("source Alembic resources are incomplete")
    yield source_root


def upgrade_database(database_path: Path) -> None:
    """使用签入的 Alembic 迁移将文件数据库升级到 head。"""

    try:
        path = database_path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with _migration_resource_root() as resource_root:
            config = Config(str(resource_root / "alembic.ini"))
            config.attributes["configure_logger"] = False
            config.set_main_option(
                "sqlalchemy.url",
                f"sqlite+pysqlite:///{path.as_posix()}",
            )
            command.upgrade(config, "head")
    except Exception:
        raise JiejianError(
            ErrorCode.STORAGE_MIGRATION,
            "数据库迁移失败",
        ) from None
