# 配置 SQLite 连接与 Session，原子建立当前工作区并核验 Worker 接纳条件。
from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing
from importlib import import_module
from pathlib import Path
from alembic import command
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.storage.base import Base
from product.backend.infrastructure.storage.schema import sqlite_schema_signature
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
    """建立当前工作区；仅对已知同代结构执行保留数据的事务升级。"""
    try:
        path = database_path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with migration_resources() as resource_root:
            history = MigrationHistory.load(resource_root)
            if path.exists():
                _upgrade_supported_workspace(path, resource_root, history.head)
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
                # 完整结构和版本核验通过后，以“不覆盖”硬链接发布，避免读到半个数据库。
                # 并发创建者已占用正式地址时只核对获胜文件，不能用 replace 覆盖其数据。
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


def _upgrade_supported_workspace(path: Path, root: Path, head: str) -> None:
    # 版本标签只是候选条件；写入前按基线的真实结构、身份和外键事实确认可升级性。
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as reader:
        try:
            revision = reader.execute("SELECT version_num FROM alembic_version").fetchall()
        except sqlite3.Error:
            return
    if revision != [("workspace_0001",)] or head == "workspace_0001":
        return
    baseline = import_module("product.backend.migrations.versions.workspace_0001")
    with closing(sqlite3.connect(":memory:")) as reference:
        for statement in baseline._STATEMENTS:
            reference.execute(statement)
        signature = sqlite_schema_signature(reference)
        identity = reference.execute("SELECT * FROM workspace_schema").fetchall()
    engine = create_sqlite_engine(path)
    try:
        with engine.connect() as connection:
            # SQLite 重建引用表需在事务外暂关外键；升级仍在单个写事务内完成并在提交前复核。
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                raw = connection.connection.driver_connection
                if (sqlite_schema_signature(raw) != signature
                        or raw.execute("SELECT * FROM workspace_schema").fetchall() != identity
                        or raw.execute("SELECT version_num FROM alembic_version").fetchall() != revision
                        or raw.execute("PRAGMA foreign_key_check").fetchone() is not None):
                    raise JiejianError(ErrorCode.STORAGE_MIGRATION, "工作区结构不受支持；数据库未修改")
                if raw.execute("SELECT 1 FROM jobs WHERE state = 'RUNNING' LIMIT 1").fetchone():
                    raise JiejianError(ErrorCode.STORAGE_MIGRATION, "仍有运行任务，请先停止原服务后升级工作区")
                config = migration_config(root, path)
                config.attributes["connection"] = connection
                command.upgrade(config, head)
                if raw.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise JiejianError(ErrorCode.STORAGE_MIGRATION, "工作区关联核验失败；升级已回滚")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
            finally:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    finally:
        engine.dispose()


def require_current_database(database_path: Path) -> None:
    """Worker 只读核验当前库，不创建文件、不升级历史库或接纳空结构。"""
    try:
        with migration_resources() as root:
            require_workspace(database_path.resolve(), revision=MigrationHistory.load(root).head)
    except JiejianError:
        raise
    except Exception:
        raise JiejianError(ErrorCode.STORAGE_MIGRATION, "数据库迁移资源不可用") from None
