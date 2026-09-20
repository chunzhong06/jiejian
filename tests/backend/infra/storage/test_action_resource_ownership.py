# 验证双身份迁移建立当前结构、拒绝无损降级并保持已有数据库事实。
import sqlite3
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from product.backend.infra.storage import upgrade_database
import hashlib
import json

from tests.fixtures.legacy_recording import _canonical, _preserved_rows, _nonempty_0003

ROOT = Path(__file__).resolve().parents[4]


def test_fresh_ownership_database_is_current_and_repeatable(tmp_path):
    database = tmp_path / "ownership.db"
    upgrade_database(database)
    upgrade_database(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0006_product_provenance"
        columns = {row[1] for row in connection.execute("PRAGMA table_info(recordings)")}
        assert {"subject_test_identity_id", "resource_owner_test_identity_id"} <= columns
        assert "test_identity_id" not in columns
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_ownership_downgrade_rejects_before_changes(tmp_path):
    database = tmp_path / "ownership.db"
    upgrade_database(database)
    with sqlite3.connect(database) as connection:
        before = tuple(connection.iterdump())
    config = Config(str(ROOT / "product/backend/alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{database.as_posix()}")
    with pytest.raises(RuntimeError, match="explicit backup"):
        command.downgrade(config, "0003_action_assurance_recording")
    with sqlite3.connect(database) as connection:
        assert tuple(connection.iterdump()) == before


def test_nonempty_0003_preserves_raw_drafts_flow_and_current_binding_hashes(tmp_path):
    from product.backend.infra.storage import create_sqlite_engine, StorageUnitOfWork
    from sqlalchemy.orm import sessionmaker
    from product.backend.workflows.recording.lifecycle import RecordingLifecycle
    database, flow_path = _nonempty_0003(tmp_path)
    original_flow = flow_path.read_bytes()
    with sqlite3.connect(database) as connection:
        original_drafts = connection.execute("SELECT recording_id, draft_json, draft_sha256 FROM flow_draft_revisions ORDER BY recording_id").fetchall()
        business = _preserved_rows(connection)
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone() == (0,)
    upgrade_database(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT recording_id, draft_json, draft_sha256 FROM flow_draft_revisions ORDER BY recording_id").fetchall() == original_drafts
        preserved = _preserved_rows(connection)
        assert {name: preserved[name] for name in business} == business
        assert all(not rows for name, (_columns, rows) in preserved.items() if name not in business)
        # 最终head新增发布收据并替换空旧Run结构；它们不属于原业务数据守恒比较。
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM check_publications").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM recordings WHERE subject_test_identity_id != resource_owner_test_identity_id").fetchone() == (0,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    from product.backend.infra.storage.db import _sqlite_schema_signature
    fresh = tmp_path / "fresh-comparison.db"
    upgrade_database(fresh)
    with sqlite3.connect(database) as upgraded, sqlite3.connect(fresh) as empty:
        assert _sqlite_schema_signature(upgraded) == _sqlite_schema_signature(empty)
    assert flow_path.read_bytes() == original_flow
    projected = RecordingLifecycle.load_final_flow(flow_path, expected_hash=hashlib.sha256(original_flow).hexdigest())
    assert projected.schema_version == "3" and projected.subject_test_identity_id == projected.resource_owner_test_identity_id
    # Repository 构造严格 current binding 会复核迁移后新 hash，而草稿保留旧 raw hash。
    engine = create_sqlite_engine(database)
    try:
        with StorageUnitOfWork(sessionmaker(engine, expire_on_commit=False)) as work:
            for recording_id, raw, digest in original_drafts:
                draft = work.flow_drafts.latest(recording_id)
                assert draft.draft_sha256 == digest and draft.raw_historical_draft_json == raw
            recording = work.recordings.get(original_drafts[0][0])
            repo = work.action_preparation
            assert repo.execution(recording.business_action_id, 1) is not None
            assert len(repo.resources(recording.business_action_id, 1)) == 1
            assert repo.evidence(recording.business_action_id, 1, "bef_"+"1"*32) is not None
            assert repo.recovery(recording.business_action_id, 1) is not None
    finally:
        engine.dispose()


@pytest.mark.parametrize("corruption", ["owner", "hash"])
def test_invalid_0003_preflight_leaves_database_byte_identical(tmp_path, corruption):
    from product.backend.core.errors import JiejianError
    database, _ = _nonempty_0003(tmp_path)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        if corruption == "owner":
            connection.execute("UPDATE action_resource_bindings SET owner_test_identity_id=?", ("tid_"+"f"*32,))
        else:
            connection.execute("UPDATE action_execution_bindings SET binding_fingerprint=?", ("f"*64,))
    before = database.read_bytes()
    with pytest.raises(JiejianError):
        upgrade_database(database)
    assert database.read_bytes() == before
