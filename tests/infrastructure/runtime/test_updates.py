import json
from pathlib import Path

import pytest

from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.runtime.updates import PortableUpdateService, finish_after_exit
from product.backend.infrastructure.storage import prepare_database
from product.backend.migrations.runtime import migration_config, migration_resources
from product.protocols.codec import encode_json
from product.backend.domain.errors import JiejianError


@pytest.fixture
def update_package(tmp_path):
    workspace = tmp_path / '业务资料'
    prepare_database(RuntimePaths(workspace).database)
    old = tmp_path / 'original'
    target = tmp_path / '新版本 with spaces'
    release = {'schema_version': '3', 'product': 'JieJian Web V1', 'version': '1.3.2', 'package_version': '1.3.2',
               'platform': 'windows', 'architecture': 'x64', 'runtime_layout_version': '3', 'python_version': '3.13.13',
               'playwright_version': '1.55.0', 'chromium_revision': '1234', 'node_version': '24.13.0', 'node_sha256': 'a'*64}
    names = ['界鉴.exe', 'app/start.ps1', 'app/product/backend/__init__.py', 'app/product/frontend/dist/index.html',
             'runtime/python/python.exe', 'runtime/node/node.exe', 'runtime/python/Lib/site-packages/jiejian-app.pth',
             'runtime/playwright/chromium-1234/chrome-win64/chrome.exe', 'app/release.json']
    for name in names:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encode_json(release) if name == 'app/release.json' else b'controlled test artifact')
    from scripts.build.resources import write_update_manifest
    write_update_manifest(target)
    manifest = json.loads((target/'app/update-manifest.json').read_bytes())
    environment = {'JIEJIAN_RUNTIME_MODE': 'portable', 'JIEJIAN_RELEASE_ROOT': str(old), 'JIEJIAN_CONTROL_ORIGIN': 'http://127.0.0.1:19845'}
    return PortableUpdateService(workspace, environment), target, manifest


@pytest.mark.parametrize('revision', ['workspace_0001', 'workspace_0002'])
def test_preview_accepts_published_origins_without_migrating_them(update_package, revision, monkeypatch):
    from alembic import command
    import sqlite3
    from contextlib import closing
    service, target, _ = update_package
    service.paths.database.unlink()
    with migration_resources() as root:
        command.upgrade(migration_config(root, service.paths.database), revision)
    with closing(sqlite3.connect(service.paths.database)) as db:
        db.execute("INSERT INTO projects(project_id,name,status,target_type,created_at_us,updated_at_us) VALUES ('kept','原应用','DRAFT','WEB',1,1)")
        db.commit()
        before = tuple(db.iterdump())
    operation = service.preview(str(target))
    assert operation['workspace_upgrade'] is True
    with closing(sqlite3.connect(service.paths.database)) as db:
        assert tuple(db.iterdump()) == before
    service.confirm(operation['operation_id'])
    calls = []
    monkeypatch.setattr('product.backend.infrastructure.runtime.updates.subprocess.CREATE_NO_WINDOW', 0, raising=False)
    monkeypatch.setattr('product.backend.infrastructure.runtime.updates.subprocess.Popen', lambda args, **kw: calls.append(args))
    finish_after_exit(service.paths.root, Path(service.environment['JIEJIAN_RELEASE_ROOT']))
    assert service.read(operation['operation_id']).phase == 'STARTING'
    assert len(calls) == 1
    prepare_database(service.paths.database)
    PortableUpdateService(service.paths.root, {'JIEJIAN_RELEASE_ROOT': str(target)}).ready()
    assert service.read(operation['operation_id']).phase == 'READY'
    with closing(sqlite3.connect(service.paths.database)) as db:
        assert db.execute('SELECT name FROM projects').fetchall() == [('原应用',)]


def test_target_must_explicitly_support_origin_and_rejects_old_manifest(update_package):
    service, target, manifest = update_package
    origin = manifest['supported_workspaces'][0]
    manifest['workspace_revision'] = origin['revision']
    manifest['workspace_digest'] = origin['schema_digest']
    manifest['supported_workspaces'] = [origin]
    path = target/'app/update-manifest.json'
    path.write_bytes(encode_json(manifest))
    before = service.paths.database.read_bytes()
    with pytest.raises(JiejianError, match='未修改'):
        service.preview(str(target))
    manifest['schema_version'] = '1'
    path.write_bytes(encode_json(manifest))
    with pytest.raises(JiejianError, match='未修改'):
        service.preview(str(target))
    assert service.paths.database.read_bytes() == before
    assert service.latest() is None


@pytest.mark.parametrize('damage', [
    'CREATE INDEX unexpected ON projects(name)',
    "UPDATE alembic_version SET version_num='unknown'",
    "UPDATE workspace_schema SET schema_digest='" + 'a'*64 + "'",
])
def test_preview_rejects_structure_drift_and_false_identity_without_writes(update_package, damage):
    import sqlite3
    from contextlib import closing
    service, target, _ = update_package
    with closing(sqlite3.connect(service.paths.database)) as db:
        db.execute(damage)
        db.commit()
    before = service.paths.database.read_bytes()
    with pytest.raises(JiejianError, match='未修改'):
        service.preview(str(target))
    assert service.paths.database.read_bytes() == before
    assert service.latest() is None


def test_preview_rejects_changed_files_without_mutation(update_package):
    service, target, manifest = update_package
    database = service.paths.database.read_bytes()
    path = target / '界鉴.exe'
    path.write_bytes(b'changed')
    with pytest.raises(JiejianError, match='未修改'):
        service.preview(str(target))
    assert service.paths.database.read_bytes() == database
    assert service.latest() is None


def test_target_with_existing_workspace_is_not_rebound(update_package):
    service, target, _ = update_package
    database = RuntimePaths(target/'var').database
    database.parent.mkdir(parents=True, exist_ok=True)
    database.write_bytes(b'other workspace')
    with pytest.raises(JiejianError):
        service.preview(str(target))
    assert database.read_bytes() == b'other workspace'
    database.unlink()
    binding = target/'var/launcher/workspace.ini'
    binding.parent.mkdir(parents=True, exist_ok=True)
    binding.write_text('[workspace]\npath=C:\\other-workspace\n', encoding='utf-16')
    with pytest.raises(JiejianError):
        service.preview(str(target))
    assert 'other-workspace' in binding.read_text('utf-16')


def test_preview_rejects_unlisted_code_and_incompatible_workspace(update_package):
    service, target, manifest = update_package
    extra = target/'app/product/unlisted.py'
    extra.write_text('arbitrary extra module', encoding='utf-8')
    with pytest.raises(JiejianError, match='未修改'):
        service.preview(str(target))
    extra.unlink()
    manifest['workspace_generation'] += 1
    (target/'app/update-manifest.json').write_bytes(encode_json(manifest))
    original = service.paths.database.read_bytes()
    with pytest.raises(JiejianError, match='未修改'):
        service.preview(str(target))
    assert service.paths.database.read_bytes() == original


def test_one_workspace_update_has_a_stable_receipt_and_starts_only_after_exit(update_package, monkeypatch):
    service, target, _ = update_package
    original = service.paths.database.read_bytes()
    plan = service.preview(str(target))
    result = service.confirm(plan['operation_id'])
    assert result['phase'] == 'WAITING_FOR_EXIT'
    assert service.confirm(plan['operation_id']) == result
    monkeypatch.setattr('product.backend.infrastructure.runtime.updates.subprocess.CREATE_NO_WINDOW', 0, raising=False)
    calls = []
    monkeypatch.setattr('product.backend.infrastructure.runtime.updates.subprocess.Popen', lambda args, **kw: calls.append(args))
    finish_after_exit(service.paths.root, Path(service.environment['JIEJIAN_RELEASE_ROOT']))
    assert service.read(plan['operation_id']).phase == 'STARTING'
    assert len(calls) == 1 and calls[0][0] == str(target / '界鉴.exe')
    assert str(service.paths.root) in calls[0]
    assert service.paths.database.read_bytes() == original
    assert (target/'var/launcher/workspace.ini').read_text('utf-16').find(str(service.paths.root)) >= 0
    new = PortableUpdateService(service.paths.root, {'JIEJIAN_RELEASE_ROOT': str(target)})
    new.ready()
    assert new.read(plan['operation_id']).phase == 'READY'
    finish_after_exit(service.paths.root, Path(service.environment['JIEJIAN_RELEASE_ROOT']))
    assert len(calls) == 1


def test_replaced_target_before_confirmation_keeps_current_service(update_package):
    service, target, _ = update_package
    plan = service.preview(str(target))
    (target/'界鉴.exe').write_bytes(b'replaced before confirmation')
    with pytest.raises(JiejianError, match='当前服务未停止'):
        service.confirm(plan['operation_id'])
    assert service.read(plan['operation_id']).phase == 'PREVIEWED'


def test_replaced_target_after_confirmation_cannot_launch(update_package, monkeypatch):
    service, target, _ = update_package
    plan = service.preview(str(target))
    service.confirm(plan['operation_id'])
    (target/'界鉴.exe').write_bytes(b'replaced after preview')
    monkeypatch.setattr('product.backend.infrastructure.runtime.updates.subprocess.Popen', lambda *a, **k: pytest.fail('invalid launch'))
    finish_after_exit(service.paths.root, Path(service.environment['JIEJIAN_RELEASE_ROOT']))
    assert service.read(plan['operation_id']).phase == 'FAILED'
    assert not (target/'var/launcher/workspace.ini').exists()


def test_explicit_original_restart_closes_interrupted_handoff_without_replay(update_package, monkeypatch):
    service, target, _ = update_package
    plan = service.preview(str(target))
    service.confirm(plan['operation_id'])
    service.accept_startup()
    assert service.read(plan['operation_id']).phase == 'FAILED'
    monkeypatch.setattr('product.backend.infrastructure.runtime.updates.subprocess.Popen', lambda *a, **k: pytest.fail('automatic retry'))
    finish_after_exit(service.paths.root, Path(service.environment['JIEJIAN_RELEASE_ROOT']))
    assert service.read(plan['operation_id']).phase == 'FAILED'
