# 验证唯一 Web V1 数据库基线、结构漂移拒绝和显式重建边界。

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.storage import Base, default_database_path, upgrade_database
from product.backend.infra.storage.db import _migration_resource_root
from product.backend.workflows.context import ApplicationCore

pytestmark = [pytest.mark.database, pytest.mark.essential]
ROOT = Path(__file__).resolve().parents[4]
CURRENT_REVISION = "0006_repair_contract_reference"
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


def test_formal_103_permission_intent_migrates_without_rule_loss(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal-103-permission.db"
    with _migration_resource_root() as root:
        config = Config(str(root / "alembic.ini"))
        config.attributes["configure_logger"] = False
        config.set_main_option(
            "sqlalchemy.url",
            f"sqlite+pysqlite:///{database.as_posix()}",
        )
        command.upgrade(config, "0002_remove_contract_workbench")
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, 'DRAFT', 'WEB', NULL, NULL, 1, 1)",
            ("migration-project", "迁移测试项目"),
        )
        connection.execute(
            "INSERT INTO permission_intents VALUES (?, ?, ?, ?, ?, ?, ?, "
            "'USER', ?, ?, 2, 2, 2)",
            (
                "pin_" + "1" * 32,
                "migration-project",
                "action_" + "2" * 32,
                "role_" + "3" * 32,
                "role_" + "4" * 32,
                "OTHER_ROLE",
                "DENY",
                "原用户确认",
                "f" * 64,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    upgrade_database(database)

    connection = sqlite3.connect(database)
    try:
        revision = connection.execute(
            "SELECT intent_id, revision, effective_state, expectation, policy_epoch, "
            "approval_json FROM permission_intent_revisions"
        ).fetchone()
        policy = connection.execute(
            "SELECT policy_epoch FROM project_policy_states WHERE project_id = ?",
            ("migration-project",),
        ).fetchone()
        binding = connection.execute(
            "SELECT status, reason_codes_json FROM intent_implementation_bindings"
        ).fetchone()
    finally:
        connection.close()
    assert revision is not None
    assert revision[:5] == ("pin_" + "1" * 32, 1, "ACTIVE", "DENY", 1)
    assert json.loads(revision[5]) == {
        "approved_at_us": 2,
        "approved_by": "原用户确认",
        "channel": "MIGRATED_USER_CONFIRMATION",
        "reason": "由界鉴 1.0.3 用户确认权限迁移",
    }
    assert policy == (1,)
    assert binding is not None and binding[0] == "UNRESOLVED"
    assert json.loads(binding[1])
    assert "permission_intents" not in _tables(database)


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


def test_formal_103_database_upgrades_without_old_governance_data_loss_to_main_chain(
    tmp_path: Path,
) -> None:
    database = tmp_path / "formal-103.db"
    with _migration_resource_root() as root:
        config = Config(str(root / "alembic.ini"))
        config.attributes["configure_logger"] = False
        config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database.as_posix()}")
        command.upgrade(config, "0001_web_v1")
    legacy_provenance = {
        "requirement_ids": ["req_" + "1" * 32],
        "candidate_ids": ["cand_" + "2" * 32],
        "sources": [
            {"source_type": "requirement_text", "locator": "requirements.md", "content_sha256": "a" * 64},
            {"source_type": "project_config", "locator": "permission-intent:legacy-project", "content_sha256": "b" * 64},
        ],
    }
    generated_project_id = "generated-project"
    generated_contract_id = (
        "generated-contract-"
        + hashlib.sha256(generated_project_id.encode("utf-8")).hexdigest()[:24]
    )
    generated_provenance = {
        "requirement_ids": [],
        "candidate_ids": [],
        "sources": [
            {
                "source_type": "project_config",
                "locator": f"permission-intent:{generated_project_id}",
                "content_sha256": "c" * 64,
            }
        ],
    }
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-project", "旧项目", "READY", "WEB", "manual-contract", 1, 1, 1),
        )
        connection.execute(
            "INSERT INTO contract_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "legacy-project",
                "manual-contract",
                1,
                "ACTIVE",
                "{}",
                json.dumps(legacy_provenance),
                None,
                "[]",
                1,
                1,
            ),
        )
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                generated_project_id,
                "内部生成项目",
                "READY",
                "WEB",
                generated_contract_id,
                1,
                2,
                2,
            ),
        )
        connection.execute(
            "INSERT INTO contract_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                generated_project_id,
                generated_contract_id,
                1,
                "ACTIVE",
                "{}",
                json.dumps(generated_provenance),
                None,
                "[]",
                2,
                2,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    upgrade_database(database)

    connection = sqlite3.connect(database)
    try:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (CURRENT_REVISION,)
        assert not {"requirements", "contract_candidates"} & _tables(database)
        assert connection.execute(
            "SELECT governed_contract_id, governed_contract_version FROM projects WHERE project_id = 'legacy-project'"
        ).fetchone() == (None, None)
        assert connection.execute(
            "SELECT governed_contract_id, governed_contract_version FROM projects "
            "WHERE project_id = ?",
            (generated_project_id,),
        ).fetchone() == (generated_contract_id, 1)
        provenance = json.loads(
            connection.execute(
                "SELECT provenance_json FROM contract_versions "
                "WHERE project_id = 'legacy-project'"
            ).fetchone()[0]
        )
        generated_provenance_after = json.loads(
            connection.execute(
                "SELECT provenance_json FROM contract_versions WHERE project_id = ?",
                (generated_project_id,),
            ).fetchone()[0]
        )
    finally:
        connection.close()
    assert provenance == {
        "sources": [
            {"source_type": "project_config", "locator": "permission-intent:legacy-project", "content_sha256": "b" * 64}
        ]
    }
    assert generated_provenance_after == {"sources": generated_provenance["sources"]}


def test_migration_directory_contains_formal_baseline_and_current_reduction() -> None:
    versions = ROOT / "product" / "backend" / "migrations" / "versions"
    assert [path.name for path in sorted(versions.glob("*.py"))] == [
        "0001_web_v1.py",
        "0002_remove_contract_workbench.py",
        "0003_permission_intent_ledger.py",
        "0004_recording_supplements.py",
        "0005_source_change_impacts.py",
        "0006_repair_contract_reference.py",
    ]


def test_relational_metadata_has_no_root_schema_version_columns() -> None:
    assert all(
        "schema_version" not in table.columns
        for table in Base.metadata.tables.values()
    )
