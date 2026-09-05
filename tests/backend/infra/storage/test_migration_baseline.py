# 验证 数据库迁移基线、旧开发库只读拒绝与精确数据库结构。

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from product.backend.composition import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import Base, default_database_path, upgrade_database


pytestmark = [pytest.mark.database, pytest.mark.essential]
ROOT = Path(__file__).resolve().parents[4]
BASE_REVISION = "0001_business_boundary_v2"
CURRENT_REVISION = "0002_business_boundary_maintenance"
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


def _upgrade_to_110(database: Path) -> None:
    config = Config(str(ROOT / "product" / "backend" / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+pysqlite:///{database.resolve().as_posix()}",
    )
    command.upgrade(config, BASE_REVISION)


def test_fresh_database_reaches_111_head_idempotently(tmp_path: Path) -> None:
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


def test_application_recreates_111_after_explicit_database_deletion(tmp_path: Path) -> None:
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


def test_repository_contains_frozen_110_and_incremental_111_migrations() -> None:
    versions = ROOT / "product" / "backend" / "migrations" / "versions"
    assert sorted(path.name for path in versions.glob("*.py")) == [
        "0001_business_boundary_v2.py",
        "0002_business_boundary_maintenance.py",
    ]


def test_official_110_business_data_upgrades_in_place(tmp_path: Path) -> None:
    database = tmp_path / "upgrade-110.db"
    _upgrade_to_110(database)
    actor_id = "bar_" + "1" * 32
    action_id = "bac_" + "2" * 32
    intent_id = "pin_" + "3" * 32
    proposal_id = "bpr_" + "4" * 32
    decision_id = "bpd_" + "5" * 32
    identity_id = "tid_" + "6" * 32
    role_id = "role_" + "7" * 32
    action_candidate_id = "action_" + "8" * 32
    source_fingerprint = "9" * 64
    approval_json = (
        '{"approved_at_us":10,"approved_by":"本机界鉴用户",'
        '"channel":"LOCAL_GUI","reason":"迁移保留审批"}'
    )
    source_snapshot = (
        '{"application_understanding_revision":1,"source_fingerprint":"'
        + source_fingerprint
        + '","candidates":[]}'
    )

    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("migration-case", "迁移测试", "DRAFT", "WEB", None, None, 1, 1),
        )
        connection.execute(
            "INSERT INTO application_understanding VALUES "
            "(?, ?, NULL, NULL, NULL, NULL, NULL, 1, ?, ?, ?, '[]', '[]', 1, ?, ?)",
            ("migration-case", "D:/migration-case", 2, source_fingerprint, 3, 1, 3),
        )
        connection.execute(
            "INSERT INTO business_actor_revisions VALUES (?, 1, ?, ?, ?, ?, 'ACTIVE', ?, ?)",
            (actor_id, "migration-case", "负责人", "负责交付", "a" * 64, approval_json, 10),
        )
        connection.execute(
            "INSERT INTO business_action_revisions VALUES "
            "(?, 1, ?, ?, ?, ?, 'EXPORT', 1, ?, ?, 'ACTIVE', ?, ?)",
            (
                action_id,
                "migration-case",
                "导出交付包",
                "导出完整项目",
                "项目交付空间",
                '[{"effect_id":"bef_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]',
                "b" * 64,
                approval_json,
                10,
            ),
        )
        connection.execute(
            "INSERT INTO business_actors VALUES (?, ?, 1, ?, ?)",
            (actor_id, "migration-case", 10, 10),
        )
        connection.execute(
            "INSERT INTO business_actions VALUES (?, ?, 1, ?, ?)",
            (action_id, "migration-case", 10, 10),
        )
        connection.execute(
            "INSERT INTO actor_implementation_bindings VALUES (?, 1, 1, ?, ?, 'CURRENT', '[]', ?, ?)",
            (actor_id, source_fingerprint, f'["{role_id}"]', "c" * 64, 10),
        )
        connection.execute(
            "INSERT INTO action_implementation_bindings VALUES (?, 1, 1, ?, ?, 'CURRENT', '[]', ?, ?)",
            (
                action_id,
                source_fingerprint,
                f'["{action_candidate_id}"]',
                "d" * 64,
                10,
            ),
        )
        connection.execute(
            "INSERT INTO boundary_proposals VALUES (?, ?, ?, '[]', '[]', '[]', '[]', ?, ?, ?)",
            (
                proposal_id,
                "migration-case",
                source_snapshot,
                "迁移前不可变提案",
                "e" * 64,
                10,
            ),
        )
        connection.execute(
            "INSERT INTO boundary_proposal_decisions VALUES (?, ?, ?, 'APPROVED', ?, ?, ?)",
            (decision_id, proposal_id, "e" * 64, "本机界鉴用户", 10, "迁移前批准"),
        )
        connection.execute(
            "INSERT INTO project_policy_states VALUES (?, 1, ?)",
            ("migration-case", 10),
        )
        connection.execute(
            "INSERT INTO permission_intent_revisions VALUES "
            "(?, 1, ?, 'ACTIVE', ?, 1, ?, 1, ?, 1, 'OWNS', 'ALLOW', ?, ?, 1, ?, ?)",
            (
                intent_id,
                "migration-case",
                actor_id,
                action_id,
                actor_id,
                '["bef_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]',
                "f" * 64,
                approval_json,
                10,
            ),
        )
        connection.execute(
            "INSERT INTO test_identities VALUES (?, ?, ?, 1, ?, NULL, NULL, NULL, NULL, ?, ?)",
            (identity_id, "migration-case", actor_id, "负责人账号", 10, 10),
        )
        connection.commit()

    upgrade_database(database)

    with sqlite3.connect(database) as connection:
        assert _revision(database) == CURRENT_REVISION
        for table in (
            "business_actors",
            "business_actions",
            "permission_intent_revisions",
            "boundary_proposals",
            "boundary_proposal_decisions",
            "test_identities",
        ):
            assert connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone() == (1,)
        actor_binding = connection.execute(
            "SELECT basis_version, candidate_snapshots_json, source_proposal_id, "
            "confirmed_at_us, binding_fingerprint "
            "FROM actor_implementation_bindings"
        ).fetchone()
        action_binding = connection.execute(
            "SELECT basis_version, candidate_snapshots_json, source_proposal_id, "
            "confirmed_at_us, binding_fingerprint "
            "FROM action_implementation_bindings"
        ).fetchone()
        assert actor_binding == (1, "[]", None, None, "c" * 64)
        assert action_binding == (1, "[]", None, None, "d" * 64)
        for table in (
            "actor_implementation_bindings",
            "action_implementation_bindings",
        ):
            foreign_keys = connection.execute(
                f'PRAGMA foreign_key_list("{table}")'
            ).fetchall()
            assert any(
                row[2] == "boundary_proposals"
                and row[3] == "source_proposal_id"
                and row[4] == "proposal_id"
                for row in foreign_keys
            )
        assert connection.execute(
            "SELECT source_snapshot_json FROM boundary_proposals"
        ).fetchone() == (source_snapshot,)


def test_current_superseded_revision_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "invalid-current.db"
    _upgrade_to_110(database)
    actor_id = "bar_" + "a" * 32
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("invalid-current", "异常迁移", "DRAFT", "WEB", None, None, 1, 1),
        )
        connection.execute(
            "INSERT INTO business_actor_revisions VALUES (?, 1, ?, ?, ?, ?, 'SUPERSEDED', '{}', ?)",
            (actor_id, "invalid-current", "旧主体", "异常当前 revision", "a" * 64, 1),
        )
        connection.execute(
            "INSERT INTO business_actors VALUES (?, ?, 1, 1, 1)",
            (actor_id, "invalid-current"),
        )
        connection.commit()

    with pytest.raises(JiejianError) as raised:
        upgrade_database(database)

    assert raised.value.code == ErrorCode.STORAGE_MIGRATION.value
    assert _revision(database) == BASE_REVISION
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT effective_state FROM business_actor_revisions"
        ).fetchone() == ("SUPERSEDED",)


def test_historical_superseded_revisions_normalize_to_active(tmp_path: Path) -> None:
    database = tmp_path / "historical-superseded.db"
    _upgrade_to_110(database)
    actor_id = "bar_" + "b" * 32
    action_id = "bac_" + "c" * 32
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("historical-case", "历史迁移", "DRAFT", "WEB", None, None, 1, 2),
        )
        for revision, state in ((1, "SUPERSEDED"), (2, "ACTIVE")):
            connection.execute(
                "INSERT INTO business_actor_revisions VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?)",
                (
                    actor_id,
                    revision,
                    "historical-case",
                    f"主体 revision {revision}",
                    "历史主体语义",
                    str(revision) * 64,
                    state,
                    revision,
                ),
            )
            connection.execute(
                "INSERT INTO business_action_revisions VALUES "
                "(?, ?, ?, ?, ?, ?, 'READ', 0, '[]', ?, ?, '{}', ?)",
                (
                    action_id,
                    revision,
                    "historical-case",
                    f"动作 revision {revision}",
                    "历史动作语义",
                    "项目资料",
                    str(revision + 2) * 64,
                    state,
                    revision,
                ),
            )
        connection.execute(
            "INSERT INTO business_actors VALUES (?, ?, 2, 1, 2)",
            (actor_id, "historical-case"),
        )
        connection.execute(
            "INSERT INTO business_actions VALUES (?, ?, 2, 1, 2)",
            (action_id, "historical-case"),
        )
        connection.commit()

    upgrade_database(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT revision, effective_state FROM business_actor_revisions "
            "ORDER BY revision"
        ).fetchall() == [(1, "ACTIVE"), (2, "ACTIVE")]
        assert connection.execute(
            "SELECT revision, effective_state FROM business_action_revisions "
            "ORDER BY revision"
        ).fetchall() == [(1, "ACTIVE"), (2, "ACTIVE")]
        for table in ("business_actor_revisions", "business_action_revisions"):
            sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            assert sql is not None and "SUPERSEDED" not in str(sql[0])


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
