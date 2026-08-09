"""SQLite 引擎、连接约束和 Alembic 迁移入口。"""

from __future__ import annotations

import sqlite3
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


def upgrade_database(database_path: Path) -> None:
    """使用签入的 Alembic 迁移将文件数据库升级到 head。"""

    try:
        path = database_path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        config_path = Path(__file__).resolve().parents[3] / "alembic.ini"
        config = Config(str(config_path))
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
