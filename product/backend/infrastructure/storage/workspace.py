# 声明当前工作区身份，并在任何业务写入前只读核验完整结构。
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from sqlalchemy import CheckConstraint, Integer, String, create_engine
from sqlalchemy.orm import Mapped, mapped_column

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.storage.base import Base
from product.backend.infrastructure.storage.schema import sqlite_schema_signature

WORKSPACE_FORMAT = "jiejian.workspace"
WORKSPACE_GENERATION = 1


class WorkspaceSchemaRow(Base):
    __tablename__ = "workspace_schema"
    __table_args__ = (CheckConstraint("singleton = 1", name="singleton"),)

    singleton: Mapped[int] = mapped_column(Integer, primary_key=True)
    format: Mapped[str] = mapped_column(String(64), nullable=False)
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_digest: Mapped[str] = mapped_column(String(64), nullable=False)


@lru_cache(maxsize=1)
def current_schema_signature():
    from product.backend.infrastructure.storage.orm_registry import load_storage_orm_mappings

    load_storage_orm_mappings()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            return sqlite_schema_signature(connection.connection.driver_connection)
    finally:
        engine.dispose()


def current_schema_digest() -> str:
    return hashlib.sha256(json.dumps(current_schema_signature(), ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()


def require_workspace(path: Path, *, revision: str) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise JiejianError(ErrorCode.STORAGE_MIGRATION, "工作区数据库尚未初始化")
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
            identity = connection.execute(
                "SELECT singleton, format, generation, schema_digest FROM workspace_schema"
            ).fetchall()
            versions = connection.execute("SELECT version_num FROM alembic_version").fetchall()
            if (identity != [(1, WORKSPACE_FORMAT, WORKSPACE_GENERATION, current_schema_digest())]
                    or versions != [(revision,)]
                    or sqlite_schema_signature(connection) != current_schema_signature()
                    or connection.execute("PRAGMA foreign_key_check").fetchone() is not None):
                raise ValueError("workspace identity or structure mismatch")
    except (OSError, sqlite3.Error, ValueError):
        raise JiejianError(ErrorCode.STORAGE_MIGRATION,
            "工作区格式或结构不受支持；数据库未修改，请使用新的运行目录") from None
