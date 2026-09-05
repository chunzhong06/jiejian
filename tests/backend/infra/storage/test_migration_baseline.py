# 验证 数据库迁移基线、旧开发库只读拒绝与精确数据库结构。

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from product.backend.composition import ApplicationCore
from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import Base, default_database_path, upgrade_database
from product.backend.infra.storage.db import _normalize_table_sql


pytestmark = [pytest.mark.database, pytest.mark.essential]
ROOT = Path(__file__).resolve().parents[4]
BASE_REVISION = "0001_business_boundary_v2"
MAINTENANCE_REVISION = "0002_business_boundary_maintenance"
CURRENT_REVISION = "0003_action_assurance_recording"
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
LEGACY_PREPARATION_MESSAGE = "存在旧录制或安全准备数据，需要人工处理；数据库未修改"
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
LEGACY_PREPARATION_TABLES = {
    "recordings",
    "flow_draft_revisions",
    "test_resources",
    "observation_bindings",
    "recovery_bindings",
    "security_effect_confirmations",
}
NEW_PREPARATION_TABLES = {
    "action_execution_bindings",
    "action_resource_bindings",
    "action_evidence_bindings",
    "action_recovery_bindings",
}
PRESERVED_BUSINESS_TABLES = (
    "projects",
    "application_understanding",
    "business_actors",
    "business_actor_revisions",
    "business_actions",
    "business_action_revisions",
    "actor_implementation_bindings",
    "action_implementation_bindings",
    "boundary_proposals",
    "boundary_proposal_decisions",
    "permission_intent_revisions",
    "project_policy_states",
    "test_identities",
)


def _revision(database: Path) -> str:
    with closing(sqlite3.connect(database)) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None
    return str(row[0])


def _tables(database: Path) -> set[str]:
    with closing(sqlite3.connect(database)) as connection:
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


def _database_state(connection: sqlite3.Connection) -> tuple[tuple[tuple[object, ...], ...], dict[str, tuple[tuple[str, ...], tuple[tuple[object, ...], ...]]]]:
    schema = tuple(
        connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
    )
    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    rows: dict[str, tuple[tuple[str, ...], tuple[tuple[object, ...], ...]]] = {}
    for table in sorted(tables):
        columns = tuple(
            str(row[1])
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        )
        order = ", ".join(f'"{column}"' for column in columns)
        values = tuple(
            connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}').fetchall()
        )
        rows[table] = (columns, values)
    return schema, rows


def _table_snapshots(
    connection: sqlite3.Connection,
    tables: tuple[str, ...],
) -> dict[str, tuple[tuple[str, ...], tuple[tuple[object, ...], ...]]]:
    all_rows = _database_state(connection)[1]
    return {table: all_rows[table] for table in tables}


def _assert_rejected_without_modification(
    database: Path,
    *,
    check_sidecars: bool = True,
    expected_message: str = INCOMPATIBLE_MESSAGE,
) -> None:
    before = database.read_bytes()
    sidecars_before = _sidecars(database)
    with closing(sqlite3.connect(database)) as connection:
        database_state_before = _database_state(connection)
    with pytest.raises(JiejianError) as raised:
        upgrade_database(database)
    assert raised.value.code == ErrorCode.STORAGE_MIGRATION.value
    assert raised.value.to_dict()["message"] == expected_message
    assert database.read_bytes() == before
    with closing(sqlite3.connect(database)) as connection:
        assert _database_state(connection) == database_state_before
    if check_sidecars:
        assert _sidecars(database) == sidecars_before


def _upgrade_to_revision(database: Path, revision: str = MAINTENANCE_REVISION) -> None:
    config = Config(str(ROOT / "product" / "backend" / "alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+pysqlite:///{database.resolve().as_posix()}",
    )
    command.upgrade(config, revision)


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
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        connection.execute(
            "CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"
        )
        connection.execute("INSERT INTO marker VALUES ('keep')")
        connection.execute("INSERT INTO alembic_version VALUES (?)", (revision,))
        connection.commit()

    _assert_rejected_without_modification(database)

    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute("SELECT value FROM marker").fetchone() == ("keep",)


def test_current_revision_with_schema_drift_is_rejected_unchanged(tmp_path: Path) -> None:
    database = tmp_path / "drift.db"
    upgrade_database(database)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("DROP TABLE actor_implementation_bindings")
        connection.commit()

    # 当前 WAL 库的只读连接可更新共享内存锁页；正式数据库文件仍不得变化。
    _assert_rejected_without_modification(database, check_sidecars=False)


def test_repository_contains_frozen_110_111_and_incremental_112_migrations() -> None:
    versions = ROOT / "product" / "backend" / "migrations" / "versions"
    assert sorted(path.name for path in versions.glob("*.py")) == [
        "0001_business_boundary_v2.py",
        "0002_business_boundary_maintenance.py",
        "0003_action_assurance_recording.py",
    ]


def test_0002_business_data_upgrades_in_place_and_preserves_rows(tmp_path: Path) -> None:
    database = tmp_path / "upgrade-110.db"
    _upgrade_to_revision(database)
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

    with closing(sqlite3.connect(database)) as connection:
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
            "INSERT INTO actor_implementation_bindings "
            "(actor_id, actor_revision, understanding_revision, source_fingerprint, "
            "role_candidate_ids_json, basis_version, source_proposal_id, confirmed_at_us, "
            "candidate_snapshots_json, binding_fingerprint, updated_at_us) "
            "VALUES (?, 1, 1, ?, ?, 1, NULL, NULL, '[]', ?, ?)",
            (actor_id, source_fingerprint, f'["{role_id}"]', "c" * 64, 10),
        )
        connection.execute(
            "INSERT INTO action_implementation_bindings "
            "(action_id, action_revision, understanding_revision, source_fingerprint, "
            "action_candidate_ids_json, basis_version, source_proposal_id, confirmed_at_us, "
            "candidate_snapshots_json, binding_fingerprint, updated_at_us) "
            "VALUES (?, 1, 1, ?, ?, 1, NULL, NULL, '[]', ?, ?)",
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

    with closing(sqlite3.connect(database)) as connection:
        preserved_before = _table_snapshots(connection, PRESERVED_BUSINESS_TABLES)

    upgrade_database(database)

    with closing(sqlite3.connect(database)) as connection:
        assert _revision(database) == CURRENT_REVISION
        assert _table_snapshots(connection, PRESERVED_BUSINESS_TABLES) == preserved_before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        tables = _tables(database)
        assert {
            "test_resources",
            "observation_bindings",
            "recovery_bindings",
            "security_effect_confirmations",
        }.isdisjoint(tables)
        assert {"recordings", "flow_draft_revisions"} <= tables
        assert NEW_PREPARATION_TABLES <= tables
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


def _seed_legacy_preparation_database(database: Path, table: str) -> None:
    _upgrade_to_revision(database)
    actor_id = "bar_" + "1" * 32
    identity_id = "tid_" + "2" * 32
    recording_id = "rec_" + "3" * 32
    resource_id = "trs_" + "4" * 32
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-case", "旧准备事实", "DRAFT", "WEB", None, None, 1, 1),
        )
        connection.execute(
            "INSERT INTO business_actor_revisions VALUES (?, 1, ?, ?, ?, ?, 'ACTIVE', '{}', ?)",
            (actor_id, "legacy-case", "协作成员", "迁移测试身份", "a" * 64, 1),
        )
        connection.execute(
            "INSERT INTO business_actors VALUES (?, ?, 1, ?, ?)",
            (actor_id, "legacy-case", 1, 1),
        )
        connection.execute(
            "INSERT INTO test_identities VALUES (?, ?, ?, 1, ?, NULL, NULL, NULL, NULL, ?, ?)",
            (identity_id, "legacy-case", actor_id, "旧测试账号", 1, 1),
        )
        connection.execute(
            "INSERT INTO recordings VALUES (?, ?, 'TARGET', NULL, ?, 'COMPLETED', ?, ?, ?, ?, ?, NULL, ?, ?, ?)",
            (recording_id, "legacy-case", "legacy-flow", 1, 1, 1, 1, 1, "[]", "[]", "[]"),
        )
        if table == "recordings":
            pass
        elif table == "flow_draft_revisions":
            connection.execute(
                "INSERT INTO flow_draft_revisions VALUES (?, 1, ?, '{}', ?, 1)",
                (recording_id, "legacy-flow", "b" * 64),
            )
        else:
            connection.execute(
                "INSERT INTO test_resources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OWNS', 'PATH', ?, ?, ?, 1, ?, ?, 1, 1)",
                (
                    resource_id,
                    "legacy-case",
                    "action_" + "5" * 32,
                    recording_id,
                    "legacy-flow",
                    "旧资源",
                    "document",
                    "resource-1",
                    identity_id,
                    "role_" + "6" * 32,
                    "path[1]",
                    "c" * 64,
                    "d" * 64,
                    "e" * 64,
                    "f" * 64,
                ),
            )
            if table == "test_resources":
                pass
            elif table == "observation_bindings":
                connection.execute(
                    "INSERT INTO observation_bindings VALUES (?, ?, ?, 'OWNER_READ', ?, ?, 'GET', ?, 1, ?, 1)",
                    ("obs_" + "7" * 32, resource_id, identity_id, recording_id, "step-1", "/items/{case_resource_id}", "8" * 64),
                )
            elif table == "recovery_bindings":
                connection.execute(
                    "INSERT INTO recovery_bindings VALUES (?, ?, ?, 'RECORDED_REQUEST', ?, ?, 'POST', ?, '{}', ?, 1)",
                    ("rcv_" + "9" * 32, resource_id, identity_id, recording_id, "step-1", "/items/{case_resource_id}", "a" * 64),
                )
            elif table == "security_effect_confirmations":
                connection.execute(
                    "INSERT INTO security_effect_confirmations VALUES (?, ?, ?, ?, ?, ?, 1)",
                    ("efc_" + "a" * 32, resource_id, "action_" + "b" * 32, "STATE_MUTATION", "[]", "c" * 64),
                )
        connection.commit()


@pytest.mark.parametrize("legacy_table", sorted(LEGACY_PREPARATION_TABLES))
def test_each_nonempty_legacy_preparation_source_is_rejected_read_only(
    tmp_path: Path,
    legacy_table: str,
) -> None:
    database = tmp_path / f"legacy-preparation-{legacy_table}.db"
    _seed_legacy_preparation_database(database, legacy_table)

    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute(f'SELECT 1 FROM "{legacy_table}" LIMIT 1').fetchone() is not None
        assert _revision(database) == MAINTENANCE_REVISION

    _assert_rejected_without_modification(
        database,
        expected_message=LEGACY_PREPARATION_MESSAGE,
    )

    with closing(sqlite3.connect(database)) as connection:
        assert _revision(database) == MAINTENANCE_REVISION
        assert connection.execute(f'SELECT 1 FROM "{legacy_table}" LIMIT 1').fetchone() is not None


def test_current_superseded_revision_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "invalid-current.db"
    _upgrade_to_revision(database, BASE_REVISION)
    actor_id = "bar_" + "a" * 32
    with closing(sqlite3.connect(database)) as connection:
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
    with closing(sqlite3.connect(database)) as connection:
        assert connection.execute(
            "SELECT effective_state FROM business_actor_revisions"
        ).fetchone() == ("SUPERSEDED",)


def test_historical_superseded_revisions_normalize_to_active(tmp_path: Path) -> None:
    database = tmp_path / "historical-superseded.db"
    _upgrade_to_revision(database, BASE_REVISION)
    actor_id = "bar_" + "b" * 32
    action_id = "bac_" + "c" * 32
    with closing(sqlite3.connect(database)) as connection:
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

    with closing(sqlite3.connect(database)) as connection:
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
    with closing(sqlite3.connect(database)) as connection:
        for table in Base.metadata.tables:
            columns = {
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            }
            assert "schema_version" not in columns


def test_table_signature_ignores_only_named_constraint_order() -> None:
    first = "CREATE TABLE t (a TEXT DEFAULT 'x, CONSTRAINT fake', b INTEGER, CONSTRAINT pk PRIMARY KEY(a, b), CONSTRAINT positive CHECK(b >= 1))"
    reordered = "CREATE TABLE t (a TEXT DEFAULT 'x, CONSTRAINT fake', b INTEGER, CONSTRAINT positive CHECK(b >= 1), CONSTRAINT pk PRIMARY KEY(a, b))"
    assert _normalize_table_sql(first) == _normalize_table_sql(reordered)
    for changed in (
        reordered.replace("b >= 1", "b >= 0"),
        reordered.replace("PRIMARY KEY(a, b)", "PRIMARY KEY(b, a)"),
        reordered.replace("x, CONSTRAINT fake", "y, CONSTRAINT fake"),
        reordered.replace("a TEXT", "a BLOB"),
    ):
        assert _normalize_table_sql(first) != _normalize_table_sql(changed)


def test_predecessor_with_extra_index_is_rejected_unchanged(tmp_path: Path) -> None:
    database = tmp_path / "predecessor-drift.db"
    _upgrade_to_revision(database)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE INDEX unexpected_project_identity ON projects(project_id)")
        connection.commit()
    _assert_rejected_without_modification(database)


def test_recording_identity_is_historical_while_business_and_draft_foreign_keys_remain(tmp_path):
    database = tmp_path / "identity-history.db"
    upgrade_database(database)
    with closing(sqlite3.connect(database)) as connection:
        for table in ("recordings", *sorted(NEW_PREPARATION_TABLES)):
            keys = connection.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
            referenced = {row[2] for row in keys}
            assert "test_identities" not in referenced
            assert {"projects", "business_action_revisions"} <= referenced
            if table != "recordings":
                assert "flow_draft_revisions" in referenced
            columns = {row[1]: row for row in connection.execute(f'PRAGMA table_info("{table}")')}
            assert columns["test_identity_id"][3] == 1
        resource_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='action_resource_bindings'").fetchone()[0]
        assert "owner_test_identity_id = test_identity_id" in resource_sql
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
