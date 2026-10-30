# 验证完整工作区基线、原子初始化及只读拒绝，不固定表数或迁移文件数。
from tests.support.builders.migration_history import migration_head, migration_history
from contextlib import closing
import sqlite3

from alembic import command
import pytest

from product.backend.domain.errors import JiejianError
from product.backend.infrastructure.storage.db import prepare_database, require_current_database
from product.backend.infrastructure.storage.workspace import current_schema_signature
from product.backend.infrastructure.storage.schema import sqlite_schema_signature
from product.backend.migrations.runtime import migration_config, migration_resources



@pytest.mark.level3
@pytest.mark.database
def test_frozen_baseline_and_direct_initialization_have_identical_schema(tmp_path):
    direct, baseline = tmp_path / "直接初始化.db", tmp_path / "baseline.db"
    prepare_database(direct)
    with migration_resources() as root:
        command.upgrade(migration_config(root, baseline), "head")
    for path in (direct, baseline):
        require_current_database(path)
        with closing(sqlite3.connect(path)) as db:
            assert sqlite_schema_signature(db) == current_schema_signature()


@pytest.mark.level3
@pytest.mark.database
def test_repeat_start_preserves_business_records_and_revision_identity(tmp_path):
    path = tmp_path / "workspace.db"
    prepare_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO projects(project_id,name,status,target_type,created_at_us,updated_at_us) "
            "VALUES ('test','项目','DRAFT','WEB',1,1)")
        db.commit()
        before = tuple(db.iterdump())
    prepare_database(path)
    require_current_database(path)
    with closing(sqlite3.connect(path)) as db:
        assert tuple(db.iterdump()) == before


@pytest.mark.level3
@pytest.mark.database
@pytest.mark.parametrize('interrupt', [False, True])
def test_same_generation_upgrade_preserves_history_and_rolls_back_as_one_unit(tmp_path, monkeypatch, interrupt):
    path = tmp_path / 'published.db'
    with migration_resources() as root:
        command.upgrade(migration_config(root, path), 'workspace_0001')
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO projects(project_id,name,status,target_type,created_at_us,updated_at_us) VALUES ('test','保留的应用','DRAFT','WEB',1,1)")
        db.execute("INSERT INTO runs(run_id,project_id,request_hash,plan_fingerprint,source_fingerprint,policy_epoch,engine_version,lifecycle,verdict,created_at_us,updated_at_us) VALUES (?, 'test', ?, ?, ?, 1, 'test', 'COMPLETED', 'PASS', 1, 1)",
            ('run_' + '1' * 32, 'a' * 64, 'b' * 64, 'c' * 64))
        db.commit()
        before = tuple(db.iterdump())
    if interrupt:
        actual_upgrade = command.upgrade
        def fail_after_ddl(*args, **kwargs):
            actual_upgrade(*args, **kwargs)
            raise RuntimeError('upgrade interrupted before commit')
        monkeypatch.setattr(command, 'upgrade', fail_after_ddl)
        with pytest.raises(JiejianError):
            prepare_database(path)
        with closing(sqlite3.connect(path)) as db:
            assert tuple(db.iterdump()) == before
    else:
        prepare_database(path)
        require_current_database(path)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('SELECT name FROM projects').fetchall() == [('保留的应用',)]
            assert db.execute('SELECT lifecycle,verdict FROM runs').fetchall() == [('COMPLETED','PASS')]
            assert db.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.level3
@pytest.mark.database
@pytest.mark.parametrize("damage", [
    "ALTER TABLE projects ADD COLUMN unexpected TEXT",
    "CREATE INDEX unexpected ON projects(name)",
    "CREATE VIEW unexpected AS SELECT project_id FROM projects",
    "UPDATE workspace_schema SET generation=99",
    "UPDATE workspace_schema SET schema_digest='unknown'",
    "UPDATE alembic_version SET version_num='old-or-future'",
    "DROP TABLE workspace_schema",
])
def test_unknown_or_drifted_database_is_rejected_without_writes(tmp_path, damage):
    path = tmp_path / "workspace.db"
    prepare_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute(damage)
        db.commit()
    before = path.read_bytes()
    for operation in (prepare_database, require_current_database):
        with pytest.raises(JiejianError):
            operation(path)
        assert path.read_bytes() == before


@pytest.mark.level3
@pytest.mark.database
@pytest.mark.parametrize("existing", [False, True])
def test_worker_never_initializes_an_unprepared_workspace(tmp_path, existing):
    path = tmp_path / "workspace.db"
    if existing:
        path.touch()
    with pytest.raises(JiejianError):
        require_current_database(path)
    assert path.exists() == existing
    if existing:
        assert path.read_bytes() == b""


@pytest.mark.level3
@pytest.mark.database
def test_interrupted_initialization_never_publishes_partial_database(tmp_path, monkeypatch):
    from sqlalchemy import MetaData

    original = MetaData.create_all
    def interrupted(self, engine, *args, **kwargs):
        original(self, engine, *args, **kwargs)
        raise RuntimeError("injected initialization failure")
    monkeypatch.setattr(MetaData, "create_all", interrupted)
    path = tmp_path / "workspace.db"
    with pytest.raises(JiejianError):
        prepare_database(path)
    assert not path.exists()
    assert not tuple(tmp_path.glob("workspace-*"))


@pytest.mark.level2
def test_schema_comparison_preserves_spaces_inside_sql_literals():
    from product.backend.infrastructure.storage.schema import normalize_sql

    assert normalize_sql("CHECK (value = 'two  spaces')") != normalize_sql("CHECK (value = 'two spaces')")
    assert normalize_sql("CHECK  (value = 'two spaces')") == normalize_sql("CHECK (value = 'two spaces')")


@pytest.mark.level3
@pytest.mark.database
@pytest.mark.parametrize("lifecycle,verdict,valid", [
    ("COMPLETED", "PASS", True), ("COMPLETED", None, False),
    ("SAFETY_STOPPED", "BLOCK", True), ("SAFETY_STOPPED", "INCONCLUSIVE", True),
    ("SAFETY_STOPPED", "PASS", False), ("RUNNING", "PASS", False),
    ("FAILED", "BLOCK", False), ("CANCELLED", "PASS", False),
])
def test_database_enforces_lifecycle_verdict_matrix(tmp_path, lifecycle, verdict, valid):
    path = tmp_path / "workspace.db"
    prepare_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO projects(project_id,name,status,target_type,created_at_us,updated_at_us) "
            "VALUES ('test','test','DRAFT','WEB',1,1)")
        values = ("run_" + "1" * 32, "test", "a" * 64, "b" * 64, "c" * 64,
            1, "test", lifecycle, verdict, 1, 1, None)
        sql = ("INSERT INTO runs (run_id,project_id,request_hash,plan_fingerprint,source_fingerprint,"
            "policy_epoch,engine_version,lifecycle,verdict,created_at_us,updated_at_us,finished_at_us) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)")
        if valid:
            db.execute(sql, values)
        else:
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(sql, values)


@pytest.mark.level1
def test_runtime_uses_the_actual_upgrade_graph():
    from product.backend.migrations.runtime import MigrationHistory, migration_resources
    scripts = migration_history()
    with migration_resources() as root:
        history = MigrationHistory.load(root)
    assert history.head == migration_head()
    assert history.revisions == {item.revision for item in scripts.walk_revisions()}


@pytest.mark.level1
@pytest.mark.parametrize('branched', [False, True])
def test_history_discovers_new_revisions_and_rejects_ambiguous_endpoints(tmp_path, branched):
    from product.backend.migrations.runtime import MigrationHistory
    versions = tmp_path / 'migrations' / 'versions'
    versions.mkdir(parents=True)
    (tmp_path / 'alembic.ini').write_text('[alembic]\nscript_location = %(here)s/migrations\n', encoding='utf-8')
    revisions = [('initial', None), ('feature', 'initial')]
    if branched:
        revisions.append(('other_feature', 'initial'))
    for revision, parent in revisions:
        (versions / f'{revision}.py').write_text(f'revision = {revision!r}\ndown_revision = {parent!r}\n', encoding='utf-8')
    if branched:
        with pytest.raises(ValueError):
            MigrationHistory.load(tmp_path)
    else:
        history = MigrationHistory.load(tmp_path)
        assert history.head == 'feature'
        assert history.revisions == {'initial', 'feature'}


@pytest.mark.level3
@pytest.mark.database
def test_uncommitted_transaction_does_not_publish_changes(core,source):
    connection=core.application_understanding.connect(source)
    project_id=connection.project.project_id
    with core.uow_factory() as work:
        project=work.projects.get(project_id)
        work.projects.replace(type(project)(**{**project.model_dump(),'name':'未提交的名称'}))
    assert core.projects.get(project_id).name!='未提交的名称'
