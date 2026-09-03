# 验证 1.1.0 单迁移基线、旧开发库只读拒绝与精确数据库结构。

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from product.backend.composition import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import Base, default_database_path, upgrade_database


pytestmark = [pytest.mark.database, pytest.mark.essential]
ROOT = Path(__file__).resolve().parents[4]
CURRENT_REVISION = "0001_business_boundary_v2"
LEGACY_REVISIONS = (
    "0001_web_v1",
    "0002_remove_contract_workbench",
    "0003_permission_intent_ledger",
    "0004_recording_supplements",
    "0005_source_change_impacts",
    "0006_repair_contract_reference",
)
INCOMPATIBLE_MESSAGE = (
    "当前运行数据属于界鉴 1.x 开发模型；1.1 使用新的业务边界模型，请创建新的运行数据目录。"
)
BOUNDARY_TABLES = {
    "business_actor_revisions",
    "business_actors",
    "business_action_revisions",
    "business_actions",
    "boundary_proposals",
    "boundary_proposal_decisions",
    "actor_implementation_bindings",
    "action_implementation_bindings",
    "permission_intent_revisions",
    "project_policy_states",
}
FORBIDDEN_TABLES = {
    "business_effects",
    "human_approvals",
    "permission_intents",
    "role_candidates",
    "action_candidates",
}


def _revision(database: Path) -> str:
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def _tables(database: Path) -> set[str]:
    with sqlite3.connect(database) as connection:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            if row[0] != "sqlite_sequence"
        }


def _sidecars(database: Path) -> dict[str, bytes | None]:
    result: dict[str, bytes | None] = {}
    for suffix in ("-wal", "-shm"):
        path = Path(str(database) + suffix)
        result[suffix] = path.read_bytes() if path.exists() else None
    return result


def _assert_rejected_without_modification(
    database: Path,
    *,
    check_sidecars: bool = True,
) -> None:
    before = database.read_bytes()
    sidecars_before = _sidecars(database)
    with pytest.raises(JiejianError) as raised:
        upgrade_database(database)
    assert raised.value.code == ErrorCode.STORAGE_MIGRATION.value
    assert raised.value.to_dict()["message"] == INCOMPATIBLE_MESSAGE
    assert database.read_bytes() == before
    if check_sidecars:
        assert _sidecars(database) == sidecars_before


def test_fresh_database_reaches_single_110_baseline_idempotently(tmp_path: Path) -> None:
    database = tmp_path / "current.db"

    upgrade_database(database)
    first = database.read_bytes()
    upgrade_database(database)

    tables = _tables(database)
    assert _revision(database) == CURRENT_REVISION
    assert tables == set(Base.metadata.tables) | {"alembic_version"}
    assert len(Base.metadata.tables) == 37
    assert BOUNDARY_TABLES <= tables
    assert not (FORBIDDEN_TABLES & tables)
    assert database.read_bytes() == first


def test_application_recreates_110_after_explicit_database_deletion(tmp_path: Path) -> None:
    var_dir = tmp_path / "var"
    initial = ApplicationCore(var_dir)
    initial.close()
    database = default_database_path(var_dir)
    database.unlink()

    restarted = ApplicationCore(var_dir)
    try:
        assert database.is_file()
        assert _revision(database) == CURRENT_REVISION
    finally:
        restarted.close()


@pytest.mark.parametrize("revision", LEGACY_REVISIONS)
def test_each_legacy_1x_revision_is_rejected_read_only(
    tmp_path: Path,
    revision: str,
) -> None:
    database = tmp_path / f"legacy-{revision}.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.execute("INSERT INTO marker VALUES ('keep')")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
        connection.commit()

    _assert_rejected_without_modification(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("keep",)


def test_current_revision_with_schema_drift_is_rejected_unchanged(tmp_path: Path) -> None:
    database = tmp_path / "drift.db"
    upgrade_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE actor_implementation_bindings")
        connection.commit()

    # 当前 WAL 库的只读连接可更新共享内存锁页；正式数据库文件仍不得变化。
    _assert_rejected_without_modification(database, check_sidecars=False)


def test_repository_contains_only_the_single_110_migration() -> None:
    versions = ROOT / "product" / "backend" / "migrations" / "versions"
    assert sorted(path.name for path in versions.glob("*.py")) == [
        "0001_business_boundary_v2.py"
    ]


def test_business_tables_do_not_carry_nested_schema_versions(tmp_path: Path) -> None:
    database = tmp_path / "columns.db"
    upgrade_database(database)
    with sqlite3.connect(database) as connection:
        for table in Base.metadata.tables:
            columns = {
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            assert "schema_version" not in columns
