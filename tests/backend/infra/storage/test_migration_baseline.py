from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import inspect

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import Base, create_sqlite_engine, upgrade_database

pytestmark = [pytest.mark.database, pytest.mark.essential]


def test_empty_database_reaches_current_head_and_is_repeatable(tmp_path: Path) -> None:
    database = tmp_path / "current.db"
    upgrade_database(database)
    upgrade_database(database)
    engine = create_sqlite_engine(database)
    try:
        assert inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == "0001_initial"
    finally:
        engine.dispose()


@pytest.mark.parametrize("revision", ["0011_contract_profile_application_core", "unknown"])
def test_incompatible_database_is_rejected_without_modification(
    tmp_path: Path,
    revision: str,
) -> None:
    database = tmp_path / f"incompatible-{revision}.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO marker VALUES ('keep')")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
        connection.commit()
    finally:
        connection.close()
    before = database.read_bytes()

    with pytest.raises(JiejianError) as error:
        upgrade_database(database)

    assert error.value.code == ErrorCode.STORAGE_MIGRATION.value
    assert "数据库格式与当前版本不兼容，请备份后重新初始化 var 目录" in str(error.value)
    assert database.read_bytes() == before
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("keep",)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (revision,)
    finally:
        connection.close()


def test_current_revision_without_current_schema_is_rejected_without_modification(
    tmp_path: Path,
) -> None:
    database = tmp_path / "current-revision-without-schema.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        connection.execute("INSERT INTO marker VALUES ('keep')")
        connection.execute("INSERT INTO alembic_version VALUES ('0001_initial')")
        connection.commit()
    finally:
        connection.close()
    before = database.read_bytes()

    with pytest.raises(JiejianError) as error:
        upgrade_database(database)

    assert error.value.code == ErrorCode.STORAGE_MIGRATION.value
    assert "数据库格式与当前版本不兼容，请备份后重新初始化 var 目录" in str(error.value)
    assert database.read_bytes() == before


def test_current_head_with_extra_table_is_rejected_without_modification(
    tmp_path: Path,
) -> None:
    database = tmp_path / "current-head-with-extra-table.db"
    upgrade_database(database)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE unexpected (value TEXT NOT NULL)")
        connection.commit()
    finally:
        connection.close()
    before = database.read_bytes()

    with pytest.raises(JiejianError) as error:
        upgrade_database(database)

    assert error.value.code == ErrorCode.STORAGE_MIGRATION.value
    assert "数据库格式与当前版本不兼容，请备份后重新初始化 var 目录" in str(error.value)
    assert database.read_bytes() == before


def test_current_metadata_has_a_single_execution_profile_table() -> None:
    assert "execution_profiles" in Base.metadata.tables
    assert "permission_execution_profiles" not in Base.metadata.tables
