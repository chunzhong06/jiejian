# 验证 0005 的精确预检、录制数据保留、DDL 回滚和新 Run 结论约束。
import importlib.util
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from alembic.migration import MigrationContext
from alembic.operations import Operations

from product.backend.infra.storage import upgrade_database
from product.backend.infra.storage.db import _sqlite_schema_signature
from tests.fixtures.action_preparation import build_preparation_harness, add_recording

ROOT = Path(__file__).resolve().parents[4]


def migration_config(database):
    config = Config(str(ROOT / "product/backend/alembic.ini"))
    config.attributes["configure_logger"] = False
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database.as_posix()}")
    return config


def old_database(tmp_path):
    database = tmp_path / "prior.db"
    command.upgrade(migration_config(database), "0004_action_resource_ownership")
    return database


def database_dump(database):
    with sqlite3.connect(database) as connection:
        return tuple(connection.iterdump())


def test_fresh_incremental_schema_and_repeat_start_match(tmp_path):
    incremental = old_database(tmp_path)
    fresh = tmp_path / "fresh.db"
    upgrade_database(incremental)
    upgrade_database(fresh)
    upgrade_database(incremental)
    with sqlite3.connect(incremental) as left, sqlite3.connect(fresh) as right:
        assert _sqlite_schema_signature(left) == _sqlite_schema_signature(right)
        assert left.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0006_product_provenance"
        columns = {row[1] for row in left.execute("PRAGMA table_info(runs)")}
        assert {"request_hash", "plan_fingerprint", "source_fingerprint", "policy_epoch"} <= columns
        assert {"contract_id", "contract_version"}.isdisjoint(columns)
        assert left.execute("PRAGMA foreign_key_check").fetchall() == []


def test_nonempty_recording_and_business_rows_remain_identical(tmp_path):
    harness = build_preparation_harness(tmp_path)
    recording = add_recording(harness)
    harness.core.recording_lifecycle.finalize(recording.recording_id, var_dir=harness.var_dir, now_us=100)
    source_path = harness.var_dir / "data/jiejian.db"
    harness.close()
    old = old_database(tmp_path)
    with sqlite3.connect(source_path) as source, sqlite3.connect(old) as destination:
        destination.execute("PRAGMA foreign_keys=OFF")
        tables = [row[0] for row in destination.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'")]
        for table in tables:
            if table == "runs":
                continue
            rows = source.execute(f'SELECT * FROM "{table}"').fetchall()
            if rows:
                placeholders = ",".join("?" for _ in rows[0])
                destination.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', rows)
        before = {table: destination.execute(f'SELECT * FROM "{table}"').fetchall() for table in tables if table != "runs"}
        assert before["recordings"] and before["flow_draft_revisions"] and before["test_identities"]
        destination.commit()
    upgrade_database(old)
    with sqlite3.connect(old) as connection:
        assert {table: connection.execute(f'SELECT * FROM "{table}"').fetchall() for table in before} == before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_nonempty_old_run_rejected_without_changes(tmp_path):
    database = old_database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO projects(project_id,name,status,target_type,created_at_us,updated_at_us) VALUES ('test','test','DRAFT','WEB',1,1)")
        connection.execute("INSERT INTO runs VALUES (?, 'test', 'old-contract', 1, 'test', 'QUEUED', NULL, 1, 1, NULL)", ("run_" + "1" * 32,))
    before = database_dump(database)
    with pytest.raises(Exception):
        upgrade_database(database)
    assert database_dump(database) == before


@pytest.mark.parametrize("table", ["evidence_index", "findings", "finding_occurrences", "run_finalizations",
    "regression_baselines", "gate_results", "change_manifests", "source_change_sets", "change_impact_assessments", "jobs"])
def test_each_dormant_table_with_valid_foreign_keys_refuses_before_ddl(tmp_path, table):
    database = old_database(tmp_path)
    run, finding, baseline, change, snapshot = "run_" + "1" * 32, "finding_" + "2" * 32, "baseline_" + "3" * 32, "c" * 36, "s" * 36
    digest = "a" * 64
    rows = {
        "runs": ((), (run, "test", "historical", 1, "test", "COMPLETED", "PASS", 1, 2, 2)),
        "evidence_index": (("runs",), ("ev_" + digest[:20], run, "case", "evidence/case.json", digest, 1, 2)),
        "findings": ((), (finding, "test", "{}", 1, 2)),
        "finding_occurrences": (("findings", "runs"), ("occ_" + "4" * 32, finding, "test", run, "PRESENT", "VULNERABLE", "high", "[]", "{}", "{}", 2)),
        "run_finalizations": (("runs",), (run, digest, "PENDING", 0, None, None, None, None, "PENDING", 0, None, None, None, None, 1, 2)),
        "regression_baselines": (("runs",), (baseline, "test", run, "[]", "[]", digest, digest, "test", '{"v":1}', "tester", "historical", 2)),
        "gate_results": (("regression_baselines",), ("gate_" + "5" * 32, baseline, "test", run, "gate-v1", digest, "[]", "PASS", 2)),
        "change_manifests": ((), (change, "test", "historical", "[]", None, "tester", 1)),
        "source_revision_snapshots": ((), (snapshot, "test", digest, 1, "[]", 1)),
        "source_change_sets": (("change_manifests", "source_revision_snapshots"), (change, "test", None, snapshot, "NO_BASELINE", "[]", "[]", "[]", digest, 1)),
        "change_impact_assessments": (("change_manifests",), (change, "test", digest, 1, "[]", "[]", digest, 1)),
        "jobs": (("runs",), ("job_" + "6" * 32, "test", run, None, "RUN", "PENDING", "old-job", digest, 0, 1, 1, None, 0, None, None, 1, 1)),
    }
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("INSERT INTO projects(project_id,name,status,target_type,created_at_us,updated_at_us) VALUES ('test','test','DRAFT','WEB',1,1)")
        inserted = set()
        def insert(name):
            if name in inserted:
                return
            dependencies, values = rows[name]
            for dependency in dependencies:
                insert(dependency)
            connection.execute(f'INSERT INTO "{name}" VALUES (' + ",".join("?" for _ in values) + ")", values)
            inserted.add(name)
        insert(table)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    before = database_dump(database)
    with pytest.raises(RuntimeError, match="STATE_PRECONDITION"):
        command.upgrade(migration_config(database), "head")
    assert database_dump(database) == before


def test_nonempty_0003_through_0005_preserves_four_bindings_and_recording_lease(tmp_path):
    from tests.backend.infra.storage.test_action_resource_ownership import _nonempty_0003
    database, flow = _nonempty_0003(tmp_path)
    raw_flow = flow.read_bytes()
    command.upgrade(migration_config(database), "0004_action_resource_ownership")
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        job = connection.execute("SELECT job_id FROM jobs WHERE recording_id IS NOT NULL LIMIT 1").fetchone()[0]
        # 历史 fixture 已含真实 Recording Job；直接形成有租约状态，不重复插入唯一录制目标。
        connection.execute("UPDATE jobs SET state='RUNNING',attempt=1,lease_owner='worker',fencing_token=7,lease_expires_at_us=999999 WHERE job_id=?", (job,))
        sequence = connection.execute("SELECT COALESCE(MAX(sequence),0)+1 FROM job_events WHERE job_id=?", (job,)).fetchone()[0]
        connection.execute("INSERT INTO job_events VALUES (?,?,?,?,?,?,?)", (job, sequence, "CLAIMED", "PENDING", "RUNNING", 2, "{}"))
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('runs','alembic_version')")]
        before = {table: connection.execute(f'SELECT * FROM "{table}"').fetchall() for table in tables}
        for table in ("action_execution_bindings", "action_resource_bindings", "action_evidence_bindings", "action_recovery_bindings", "jobs", "job_events"):
            assert before[table]
    upgrade_database(database)
    with sqlite3.connect(database) as connection:
        assert {table: connection.execute(f'SELECT * FROM "{table}"').fetchall() for table in before} == before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    fresh = tmp_path / "fresh-comparison.db"
    upgrade_database(fresh)
    with sqlite3.connect(database) as left, sqlite3.connect(fresh) as right:
        assert _sqlite_schema_signature(left) == _sqlite_schema_signature(right)
    assert flow.read_bytes() == raw_flow


def test_schema_drift_rejected_before_ddl(tmp_path):
    database = old_database(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unknown_table(value TEXT)")
    before = database_dump(database)
    with pytest.raises(Exception):
        command.upgrade(migration_config(database), "head")
    assert database_dump(database) == before


def test_mid_ddl_failure_rolls_back_old_structure_and_marker(tmp_path, monkeypatch):
    database = old_database(tmp_path)
    path = ROOT / "product/backend/migrations/versions/0005_verification_loop_v3.py"
    spec = importlib.util.spec_from_file_location("verification_migration_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    before = database_dump(database)
    engine = create_engine(f"sqlite+pysqlite:///{database.as_posix()}")
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        monkeypatch.setattr(module, "op", Operations(context))
        def fail_after_run_rebuild():
            raise RuntimeError("injected publication DDL failure")
        monkeypatch.setattr(module, "_create_publications", fail_after_run_rebuild)
        with pytest.raises(RuntimeError, match="injected publication"):
            with context.begin_transaction(_per_migration=True):
                module.upgrade()
    engine.dispose()
    assert database_dump(database) == before


def test_downgrade_rejected_before_ddl(tmp_path):
    database = tmp_path / "fresh.db"
    upgrade_database(database)
    before = database_dump(database)
    with pytest.raises(RuntimeError, match="explicit backup"):
        command.downgrade(migration_config(database), "0004_action_resource_ownership")
    assert database_dump(database) == before


@pytest.mark.parametrize("lifecycle,verdict,valid", [
    ("COMPLETED", "PASS", True), ("COMPLETED", None, False),
    ("SAFETY_STOPPED", "BLOCK", True), ("SAFETY_STOPPED", "INCONCLUSIVE", True),
    ("SAFETY_STOPPED", "PASS", False), ("RUNNING", "PASS", False),
    ("FAILED", "BLOCK", False), ("CANCELLED", "PASS", False),
])
def test_database_enforces_lifecycle_verdict_matrix(tmp_path, lifecycle, verdict, valid):
    database = tmp_path / "matrix.db"
    upgrade_database(database)
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO projects(project_id,name,status,target_type,created_at_us,updated_at_us) VALUES ('test','test','DRAFT','WEB',1,1)")
        values = ("run_" + "1" * 32, "test", "a" * 64, "b" * 64, "c" * 64, 1, "test", lifecycle, verdict, 1, 1, None)
        if valid:
            connection.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
        else:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)
