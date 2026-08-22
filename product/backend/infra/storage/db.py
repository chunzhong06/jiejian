# =============================================================================
# 数据库运行时与迁移入口
#
# 定位
#   SQLite 连接语义、SQLAlchemy Session 与 Alembic 资源之间的基础设施边界
#
# 职责
#   配置连接约束｜创建 Session factory｜定位并执行完整 migration 链
#
# 边界
#   不猜测不兼容迁移；数据库版本、约束或 migration 资源不符时在启动阶段明确失败。
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
from sqlalchemy import Engine, Table, UniqueConstraint, create_engine, event
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.paths import RuntimePaths

SQLITE_BUSY_TIMEOUT_MS = 5_000
_CURRENT_MIGRATION_REVISION = "0001_initial"
_INCOMPATIBLE_DATABASE_MESSAGE = "数据库格式与当前版本不兼容，请备份后重新初始化 var 目录"


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


@contextmanager
def _migration_resource_root() -> Iterator[Path]:
    """提供源码或已安装包中的成对 Alembic 资源目录。"""

    packaged_root = files("product.backend")
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

    source_root = Path(__file__).resolve().parents[2]
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
        _check_database_compatibility(path)
        with _migration_resource_root() as resource_root:
            config = Config(str(resource_root / "alembic.ini"))
            config.attributes["configure_logger"] = False
            config.set_main_option(
                "sqlalchemy.url",
                f"sqlite+pysqlite:///{path.as_posix()}",
            )
            command.upgrade(config, "head")
    except JiejianError:
        raise
    except Exception:
        raise JiejianError(
            ErrorCode.STORAGE_MIGRATION,
            "数据库迁移失败",
        ) from None


def _check_database_compatibility(path: Path) -> None:
    """在 Alembic 写入前只读拒绝开发期或未知数据库。"""

    if not path.exists():
        return
    try:
        if path.stat().st_size == 0:
            return
        uri = f"file:{path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
                if row[0] != "sqlite_sequence"
            }
            if not tables:
                return
            if "alembic_version" not in tables:
                raise JiejianError(ErrorCode.STORAGE_MIGRATION, _INCOMPATIBLE_DATABASE_MESSAGE)
            revisions = tuple(
                row[0]
                for row in connection.execute("SELECT version_num FROM alembic_version")
            )
            if revisions != (_CURRENT_MIGRATION_REVISION,):
                raise JiejianError(ErrorCode.STORAGE_MIGRATION, _INCOMPATIBLE_DATABASE_MESSAGE)
            from product.backend.infra.storage import Base

            expected_tables = set(Base.metadata.tables) | {"alembic_version"}
            if tables != expected_tables:
                raise JiejianError(ErrorCode.STORAGE_MIGRATION, _INCOMPATIBLE_DATABASE_MESSAGE)
            expected_columns = {
                table_name: {column.name for column in table.columns}
                for table_name, table in Base.metadata.tables.items()
            }
            expected_columns["alembic_version"] = {"version_num"}
            for table_name, columns in expected_columns.items():
                quoted_table_name = _quote_sqlite_identifier(table_name)
                actual_columns = {
                    row[1]
                    for row in connection.execute(f"PRAGMA table_info({quoted_table_name})")
                }
                if actual_columns != columns:
                    raise JiejianError(
                        ErrorCode.STORAGE_MIGRATION,
                        _INCOMPATIBLE_DATABASE_MESSAGE,
                    )
                if table_name != "alembic_version" and not _has_expected_unique_cardinality(
                    connection,
                    Base.metadata.tables[table_name],
                ):
                    raise JiejianError(
                        ErrorCode.STORAGE_MIGRATION,
                        _INCOMPATIBLE_DATABASE_MESSAGE,
                    )
        finally:
            connection.close()
    except JiejianError:
        raise
    except (OSError, sqlite3.DatabaseError):
        raise JiejianError(ErrorCode.STORAGE_MIGRATION, _INCOMPATIBLE_DATABASE_MESSAGE) from None


def _quote_sqlite_identifier(identifier: str) -> str:
    """Quote a metadata-controlled SQLite identifier for a PRAGMA expression."""

    if "\x00" in identifier:
        raise ValueError("SQLite identifiers cannot contain NUL")
    return '"' + identifier.replace('"', '""') + '"'


def _has_expected_unique_cardinality(
    connection: sqlite3.Connection,
    table: Table,
) -> bool:
    """核对会改变业务关系基数的唯一列组合与部分唯一语义。"""

    expected = {
        (tuple(column.name for column in constraint.columns), False)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    expected.update(
        (
            tuple(column.name for column in index.columns),
            index.dialect_options["sqlite"].get("where") is not None,
        )
        for index in table.indexes
        if index.unique
    )
    quoted_table_name = _quote_sqlite_identifier(table.name)
    actual: set[tuple[tuple[str, ...], bool]] = set()
    for index_row in connection.execute(f"PRAGMA index_list({quoted_table_name})"):
        if not index_row[2] or index_row[3] == "pk":
            continue
        quoted_index_name = _quote_sqlite_identifier(index_row[1])
        columns = tuple(
            row[2]
            for row in connection.execute(f"PRAGMA index_info({quoted_index_name})")
        )
        actual.add((columns, bool(index_row[4])))
    return actual == expected
