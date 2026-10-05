# 在隔离目录验证启动生成物归属、共享引用、按项删除、退出证明及目录联接边界。
import json
import os
from pathlib import Path
import subprocess

import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.maintenance import LocalMaintenanceService
from product.backend.infra.runtime.maintenance_assets import exclusive_file, mark_runtime_idle


def record(path, **values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'schema_version':'1', **values}), encoding='utf-8')


def build(root, name):
    path = root / 'frontend/builds' / name
    record(path / 'receipt.json', build_digest=name, dependency_digest='deps')
    (path / 'dist').mkdir()
    (path / 'dist/index.html').write_text(name, encoding='utf-8')
    return path


def source(var, root, current):
    components = {key:{'executable':str(root / 'tools' / key / 'current/tool.exe')} for key in ('python','uv','node','pnpm','playwright')}
    record(var / 'runtime/source/receipt.json', runtime_mode='development', var_dir=str(var), **components)
    record(var / 'runtime/build/frontend-receipt.json', shared_build=str(current), dist=str(var / 'runtime/frontend'))


@pytest.fixture
def setup(tmp_path):
    root, var = tmp_path / 'shared', tmp_path / 'instance'
    current, old = build(root,'current'), build(root,'old')
    source(var,root,current)
    service = LocalMaintenanceService(var,development_root=root)
    return service, root, var, current, old


def test_only_unreferenced_owned_builds_and_cache_are_removed(setup):
    service,root,var,current,old = setup
    cache = root / 'cache/downloads'
    record(cache / '.startup-owned.json',kind='startup-cache',name='downloads')
    (cache/'archive.zip').write_bytes(b'cache')
    unknown = root/'frontend/builds/unknown'
    unknown.mkdir()
    kept = []
    for base in (var,root):
        for relative in ('audit/result.txt','design/demo.html','handoff/notes.txt','test/data.txt','release/package.zip','data/record.txt'):
            path=base/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('keep',encoding='utf-8');kept.append(path)
    preview=service.preview('clear-all')
    assert {item['relative_path'] for item in preview['targets']} == {'共享启动目录/frontend/builds/old','共享启动目录/cache/downloads'}
    service.execute(preview['plan_id'])
    assert current.is_dir() and unknown.is_dir() and not old.exists() and not cache.exists()
    assert all(path.read_text(encoding='utf-8')=='keep' for path in kept)


def test_reference_added_after_preview_protects_whole_build(setup):
    service,root,var,current,old=setup
    preview=service.preview('clear-all')
    other=var.parent/'other'
    source(other,root,old)
    record(root/'state/startup-instances/other.json',kind='startup-instance',var_dir=str(other))
    result=service.execute(preview['plan_id'])
    assert result['counts']['SKIPPED_IN_USE']==1
    assert (old/'dist/index.html').read_text()=='old'


def test_live_reference_survives_current_receipt_switch(setup):
    service,root,var,current,old=setup
    service.assets.retain_live_references()
    try:
        source(var,root,old)
        assert service.preview('clear-all')['targets']==[]
    finally:
        service.assets.close()
    assert len(service.preview('clear-all')['targets'])==1


def test_prepare_lock_blocks_cleanup_before_any_deletion(setup):
    service,root,_,_,old=setup
    preview=service.preview('clear-all')
    with exclusive_file(root/'locks/prepare.lock'):
        with pytest.raises(JiejianError):
            service.execute(preview['plan_id'])
    assert old.exists()
    assert service.execute(preview['plan_id'])['counts']['DELETED']==1


def test_selected_items_and_receipt_recovery_never_reexecute(setup,monkeypatch):
    service,root,var,_,old=setup
    another=build(root,'another')
    preview=service.preview('clear-all')
    chosen=next(item['item_id'] for item in preview['targets'] if item['relative_path'].endswith('/old'))
    with pytest.raises(JiejianError):
        service.execute(preview['plan_id'],item_ids=['not-in-plan'])
    first=service.execute(preview['plan_id'],item_ids=[chosen])
    assert not old.exists() and another.exists()
    monkeypatch.setattr(service,'_execute_candidate',lambda _:pytest.fail('must not delete again'))
    assert service.execute(preview['plan_id'])==first
    restarted=LocalMaintenanceService(var,development_root=root)
    assert restarted.outcome(preview['plan_id'])['result']['counts']['DELETED']==1
    assert another.exists()


def test_runtime_idle_requires_closed_tree_and_preserves_failed_credential_cleanup(setup,monkeypatch):
    service,_,var,_,_=setup
    temp=service.paths.temp/'process-one'
    record(temp/'.runtime-process.json',kind='runtime-process',name=temp.name,kernel_identity={'kind':'fixture'})
    monkeypatch.setattr('product.backend.infra.runtime.process.tree.kernel_tree_has_exited',lambda _:False)
    assert not service.preview('clear-temporary')['targets']
    monkeypatch.setattr('product.backend.infra.runtime.process.tree.kernel_tree_has_exited',lambda _:True)
    ready=service.paths.identity_preparations/'prep-done';ready.mkdir()
    mark_runtime_idle(var,ready,'identity-preparation')
    unfinished=service.paths.identity_preparations/'prep-unconfirmed';unfinished.mkdir()
    result=service.execute(service.preview('clear-temporary')['plan_id'])
    assert result['counts']['DELETED']==2
    assert unfinished.exists()


@pytest.mark.skipif(os.name!='nt',reason='Windows junction')
def test_junction_inside_owned_build_cannot_reach_excluded_design(setup):
    service,_,var,_,old=setup
    design=var/'design';design.mkdir();(design/'unique.html').write_text('keep')
    result=subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(old/'alias'),str(design)],capture_output=True,check=False)
    assert result.returncode==0
    preview=service.preview('clear-all')
    assert preview['targets']==[]
    assert (design/'unique.html').read_text()=='keep'
    assert any(item['state']=='UNKNOWN' for item in preview['status']['inventory'])


def test_unregistered_files_in_known_cache_and_log_folders_are_not_owned(setup):
    from product.backend.infra.runtime.generated_files import register_generated_file
    service,_,_,_,_=setup
    owned=service.paths.assistant_cache/'owned.json';owned.write_text('{}')
    manual=service.paths.assistant_cache/'manual.json';manual.write_text('{}')
    log=service.paths.app_logs/'manual.log';log.write_text('keep')
    register_generated_file(service.paths.root,owned,'assistant-cache')
    preview=service.preview('clear-assistant-cache')
    assert [item['relative_path'] for item in preview['targets']]==['cache/assistant/owned.json']
    service.execute(preview['plan_id'])
    assert manual.exists() and log.exists() and not owned.exists()


def test_ownership_removed_after_preview_prevents_deletion(setup):
    from product.backend.infra.runtime.generated_files import register_generated_file, forget_generated_file
    service, _, var, _, _ = setup
    path = service.paths.assistant_cache / 'registered.bin'
    path.write_bytes(b'keep')
    register_generated_file(var, path, 'assistant-cache')
    plan = service.preview('clear-assistant-cache')
    forget_generated_file(var, path, 'assistant-cache')
    assert service.execute(plan['plan_id'])['counts']['SKIPPED_CHANGED'] == 1
    assert path.read_bytes() == b'keep'


@pytest.mark.skipif(os.name!='nt',reason='Windows mapped image')
def test_running_interpreter_is_not_available_for_component_cleanup():
    import sys
    from product.backend.infra.runtime.maintenance_assets import component_in_use
    assert component_in_use(Path(sys.executable))
