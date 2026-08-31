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
import tempfile
from collections import Counter
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
from product.backend.infra.storage.base import Base
from product.backend.infra.storage.orm_registry import load_storage_orm_mappings

SQLITE_BUSY_TIMEOUT_MS = 5_000
_CURRENT_MIGRATION_REVISION = "0006_repair_contract_reference"
_UPGRADEABLE_MIGRATION_REVISIONS = frozenset(
    {
        "0001_web_v1",
        "0002_remove_contract_workbench",
        "0003_permission_intent_ledger",
        "0004_recording_supplements",
        "0005_source_change_impacts",
    }
)
_INCOMPATIBLE_DATABASE_MESSAGE = (
    "旧开发数据库或当前数据库结构与 Web V1 基线不兼容，请备份后重新初始化 var"
)
_EXPECTED_TRIGGER_SQL = {
    "projects_governed_binding_insert": (
        "CREATE TRIGGER projects_governed_binding_insert "
        "BEFORE INSERT ON projects BEGIN "
        "SELECT RAISE(ABORT, 'governed contract binding must be paired') "
        "WHERE (NEW.governed_contract_id IS NULL) != "
        "(NEW.governed_contract_version IS NULL) "
        "OR (NEW.governed_contract_version IS NOT NULL "
        "AND NEW.governed_contract_version < 1); END"
    ),
    "projects_governed_binding_update": (
        "CREATE TRIGGER projects_governed_binding_update "
        "BEFORE UPDATE OF governed_contract_id, governed_contract_version "
        "ON projects BEGIN "
        "SELECT RAISE(ABORT, 'governed contract binding must be paired') "
        "WHERE (NEW.governed_contract_id IS NULL) != "
        "(NEW.governed_contract_version IS NULL) "
        "OR (NEW.governed_contract_version IS NOT NULL "
        "AND NEW.governed_contract_version < 1); END"
    ),
}


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
        with _migration_resource_root() as resource_root:
            _check_database_compatibility(path, resource_root=resource_root)
            config = Config(str(resource_root / "alembic.ini"))
            config.attributes["configure_logger"] = False
            config.set_main_option(
                "sqlalchemy.url",
                f"sqlite+pysqlite:///{path.as_posix()}",
            )
            command.upgrade(config, "head")
        _check_database_compatibility(path)
    except JiejianError:
        raise
    except Exception:
        raise JiejianError(
            ErrorCode.STORAGE_MIGRATION,
            "数据库迁移失败",
        ) from None


def _check_database_compatibility(
    path: Path,
    *,
    resource_root: Path | None = None,
) -> None:
    """只读核验当前 head 或已签入的精确可升级基线。"""

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
            if len(revisions) != 1:
                raise JiejianError(ErrorCode.STORAGE_MIGRATION, _INCOMPATIBLE_DATABASE_MESSAGE)
            revision = revisions[0]
            if revision in _UPGRADEABLE_MIGRATION_REVISIONS:
                if resource_root is None or not _matches_migration_revision(
                    connection,
                    revision,
                    resource_root,
                    path.parent,
                ):
                    raise JiejianError(
                        ErrorCode.STORAGE_MIGRATION,
                        _INCOMPATIBLE_DATABASE_MESSAGE,
                    )
                return
            if revision != _CURRENT_MIGRATION_REVISION:
                raise JiejianError(ErrorCode.STORAGE_MIGRATION, _INCOMPATIBLE_DATABASE_MESSAGE)
            load_storage_orm_mappings()
            metadata_tables = dict(Base.metadata.tables)
            expected_tables = set(metadata_tables) | {"alembic_version"}
            if tables != expected_tables:
                raise JiejianError(ErrorCode.STORAGE_MIGRATION, _INCOMPATIBLE_DATABASE_MESSAGE)
            triggers = {
                str(row[0]): _normalize_sql(str(row[1]))
                for row in connection.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type = 'trigger'"
                )
            }
            expected_triggers = {
                name: _normalize_sql(statement)
                for name, statement in _EXPECTED_TRIGGER_SQL.items()
            }
            if triggers != expected_triggers:
                raise JiejianError(ErrorCode.STORAGE_MIGRATION, _INCOMPATIBLE_DATABASE_MESSAGE)
            expected_columns = {
                table_name: {column.name for column in table.columns}
                for table_name, table in metadata_tables.items()
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
                if table_name != "alembic_version" and not _has_expected_indexes(
                    connection,
                    metadata_tables[table_name],
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


def _matches_migration_revision(
    connection: sqlite3.Connection,
    revision: str,
    resource_root: Path,
    temporary_parent: Path,
) -> bool:
    """用同一签入 migration 构造参考结构，拒绝伪装成旧 revision 的漂移数据库。"""

    handle = tempfile.NamedTemporaryFile(
        prefix="jiejian-migration-reference-",
        suffix=".db",
        dir=temporary_parent,
        delete=False,
    )
    reference_path = Path(handle.name)
    handle.close()
    try:
        config = Config(str(resource_root / "alembic.ini"))
        config.attributes["configure_logger"] = False
        config.set_main_option(
            "sqlalchemy.url",
            f"sqlite+pysqlite:///{reference_path.as_posix()}",
        )
        command.upgrade(config, revision)
        reference = sqlite3.connect(
            f"file:{reference_path.as_posix()}?mode=ro",
            uri=True,
        )
        try:
            return _sqlite_schema_signature(connection) == _sqlite_schema_signature(reference)
        finally:
            reference.close()
    finally:
        reference_path.unlink(missing_ok=True)


def _sqlite_schema_signature(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        sorted(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                _normalize_sql(str(row[3])),
            )
            for row in connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE type IN ('table', 'index', 'trigger') "
                "AND name NOT LIKE 'sqlite_%' AND sql IS NOT NULL"
            )
        )
    )


def _quote_sqlite_identifier(identifier: str) -> str:
    """Quote a metadata-controlled SQLite identifier for a PRAGMA expression."""

    if "\x00" in identifier:
        raise ValueError("SQLite identifiers cannot contain NUL")
    return '"' + identifier.replace('"', '""') + '"'


def _normalize_sql(statement: str) -> str:
    """折叠 SQLite 保存 SQL 的无意义空白，保留结构比较语义。"""

    return " ".join(statement.split())


def _has_expected_indexes(
    connection: sqlite3.Connection,
    table: Table,
) -> bool:
    """核对全部显式索引及唯一关系基数，不接受额外索引。"""

    expected = Counter(
        (tuple(column.name for column in constraint.columns), True, False)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    expected.update(
        (
            tuple(column.name for column in index.columns),
            bool(index.unique),
            index.dialect_options["sqlite"].get("where") is not None,
        )
        for index in table.indexes
    )
    return _sqlite_indexes(connection, table.name) == expected


def _sqlite_indexes(
    connection: sqlite3.Connection,
    table_name: str,
) -> Counter[tuple[tuple[str, ...], bool, bool]]:
    quoted_table_name = _quote_sqlite_identifier(table_name)
    actual: Counter[tuple[tuple[str, ...], bool, bool]] = Counter()
    for index_row in connection.execute(f"PRAGMA index_list({quoted_table_name})"):
        if index_row[3] == "pk":
            continue
        quoted_index_name = _quote_sqlite_identifier(index_row[1])
        columns = tuple(
            row[2]
            for row in connection.execute(f"PRAGMA index_info({quoted_index_name})")
        )
        actual[(columns, bool(index_row[2]), bool(index_row[4]))] += 1
    return actual
