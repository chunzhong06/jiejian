# 配置 SQLite 连接与 Session，原子建立当前工作区并核验 Worker 接纳条件。
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from alembic import command
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.storage.base import Base
from product.backend.infrastructure.storage.workspace import (
    WORKSPACE_FORMAT, WORKSPACE_GENERATION, WorkspaceSchemaRow,
    current_schema_digest, require_workspace,
)
from product.backend.migrations.runtime import MigrationHistory, migration_config, migration_resources

SQLITE_BUSY_TIMEOUT_MS = 5_000


def default_database_path(var_dir: Path) -> Path:
    """返回唯一 data 分区中的数据库路径；不读取旧 VarDir 根布局。"""

    return RuntimePaths(var_dir).database


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


def prepare_database(database_path: Path) -> None:
    """原子建立当前完整工作区；已有文件只核验，不隐式转换或覆盖。"""
    try:
        path = database_path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with migration_resources() as resource_root:
            history = MigrationHistory.load(resource_root)
            if path.exists():
                require_workspace(path, revision=history.head)
                return
            with tempfile.TemporaryDirectory(prefix="workspace-", dir=path.parent) as temporary:
                staged = Path(temporary) / "workspace.db"
                engine = create_sqlite_engine(staged)
                try:
                    digest = current_schema_digest()
                    Base.metadata.create_all(engine)
                    with engine.begin() as connection:
                        connection.execute(WorkspaceSchemaRow.__table__.insert().values(
                            singleton=1, format=WORKSPACE_FORMAT,
                            generation=WORKSPACE_GENERATION, schema_digest=digest))
                finally:
                    engine.dispose()
                command.stamp(migration_config(resource_root, staged), history.head)
                require_workspace(staged, revision=history.head)
                # 不覆盖并发创建的工作区；完整文件形成后才发布到正式地址。
                try:
                    os.link(staged, path)
                except FileExistsError:
                    require_workspace(path, revision=history.head)
    except JiejianError:
        raise
    except Exception:
        raise JiejianError(
            ErrorCode.STORAGE_MIGRATION,
            "工作区数据库初始化失败",
        ) from None


def require_current_database(database_path: Path) -> None:
    """Worker 只读核验当前库，不创建文件、不升级历史库或接纳空结构。"""
    try:
        with migration_resources() as root:
            require_workspace(database_path.resolve(), revision=MigrationHistory.load(root).head)
    except JiejianError:
        raise
    except Exception:
        raise JiejianError(ErrorCode.STORAGE_MIGRATION, "数据库迁移资源不可用") from None
