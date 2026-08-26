# 验证唯一 Web V1 数据库基线、结构漂移拒绝和显式重建边界。

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import Base, default_database_path, upgrade_database
from product.backend.workflows.context import ApplicationCore

pytestmark = [pytest.mark.database, pytest.mark.essential]
ROOT = Path(__file__).resolve().parents[4]
CURRENT_REVISION = "0001_web_v1"
INCOMPATIBLE_MESSAGE = (
    "旧开发数据库或当前数据库结构与 Web V1 基线不兼容，请备份后重新初始化 var"
)


def _revision(database: Path) -> str:
    connection = sqlite3.connect(database)
    try:
        value = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
    finally:
        connection.close()
    assert value is not None
    return str(value[0])


def _tables(database: Path) -> set[str]:
    connection = sqlite3.connect(database)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            if row[0] != "sqlite_sequence"
        }
    finally:
        connection.close()


def _assert_rejected_without_modification(database: Path) -> None:
    before = database.read_bytes()
    with pytest.raises(JiejianError) as error:
        upgrade_database(database)
    assert error.value.code == ErrorCode.STORAGE_MIGRATION.value
    assert INCOMPATIBLE_MESSAGE in str(error.value)
    assert database.read_bytes() == before


def test_empty_database_reaches_web_v1_and_repeat_upgrade_is_idempotent(
    tmp_path: Path,
) -> None:
    database = tmp_path / "current.db"

    upgrade_database(database)
    first = database.read_bytes()
    upgrade_database(database)

    assert _revision(database) == CURRENT_REVISION
    assert _tables(database) == set(Base.metadata.tables) | {"alembic_version"}
    assert database.read_bytes() == first


def test_application_recreates_web_v1_after_explicit_database_deletion(
    tmp_path: Path,
) -> None:
    var_dir = tmp_path / "var"
    initial = ApplicationCore(var_dir)
    initial.close()
    database = default_database_path(var_dir)
    database.unlink()
    assert not database.exists()

    restarted = ApplicationCore(var_dir)
    try:
        assert database.is_file()
        assert _revision(database) == CURRENT_REVISION
    finally:
        restarted.close()


@pytest.mark.parametrize("revision", ["0008_ai_assistance_settings", "unknown"])
def test_old_or_unknown_revision_is_rejected_without_modification(
    tmp_path: Path,
    revision: str,
) -> None:
    database = tmp_path / f"incompatible-{revision}.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.execute("INSERT INTO marker VALUES ('keep')")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
        connection.commit()
    finally:
        connection.close()

    _assert_rejected_without_modification(database)

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("keep",)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (revision,)
    finally:
        connection.close()


@pytest.mark.parametrize(
    "statements",
    [
        ("DROP TABLE ai_assistance_settings",),
        ("ALTER TABLE llm_profiles DROP COLUMN reasoning_effort",),
        (
            "DROP INDEX uq_contract_versions_active",
            "CREATE UNIQUE INDEX uq_contract_versions_active "
            "ON contract_versions (project_id, contract_id)",
        ),
    ],
    ids=["missing-table", "missing-column", "wrong-unique-index"],
)
def test_current_revision_with_required_structure_drift_is_rejected_unchanged(
    tmp_path: Path,
    statements: tuple[str, ...],
) -> None:
    database = tmp_path / "required-structure-drift.db"
    upgrade_database(database)
    connection = sqlite3.connect(database)
    try:
        for statement in statements:
            connection.execute(statement)
        connection.commit()
    finally:
        connection.close()

    _assert_rejected_without_modification(database)


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE unexpected (value TEXT NOT NULL)",
        "CREATE INDEX unexpected_projects_name ON projects (name)",
    ],
    ids=["extra-table", "extra-index"],
)
def test_current_revision_with_extra_structure_is_rejected_unchanged(
    tmp_path: Path,
    statement: str,
) -> None:
    database = tmp_path / "extra-structure.db"
    upgrade_database(database)
    connection = sqlite3.connect(database)
    try:
        connection.execute(statement)
        connection.commit()
    finally:
        connection.close()

    _assert_rejected_without_modification(database)


def test_migration_directory_contains_only_web_v1_baseline() -> None:
    versions = ROOT / "product" / "backend" / "migrations" / "versions"
    assert [path.name for path in sorted(versions.glob("*.py"))] == [
        "0001_web_v1.py"
    ]


def test_relational_metadata_has_no_root_schema_version_columns() -> None:
    assert all(
        "schema_version" not in table.columns
        for table in Base.metadata.tables.values()
    )
