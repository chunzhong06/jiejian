"""Linux完整程序树校验：加快目录核对后仍拒绝遗漏、篡改、路径别名和链接。"""
import hashlib
import json
from pathlib import Path
import runpy

import pytest


ENTRY = runpy.run_path(str(Path(__file__).resolve().parents[3]/'product/launcher/linux/start.py'))
VERIFY = ENTRY['verify_files']


@pytest.fixture
def bundle(tmp_path):
    (tmp_path/'app').mkdir()
    (tmp_path/'runtime/node').mkdir(parents=True)
    files = {'start.sh':b'#!/bin/sh\n','app/release.json':b'{}','runtime/node/node':b'fixed runtime'}
    for name, content in files.items():
        (tmp_path/name).write_bytes(content)
    manifest = dict(schema_version='2',document_type='jiejian.portable-update',files=[
        dict(relative_path=name,sha256=hashlib.sha256(content).hexdigest()) for name,content in files.items()])
    (tmp_path/'app/update-manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    return tmp_path


def test_exact_regular_tree_passes(bundle):
    assert len(VERIFY(bundle)['files']) == 3


@pytest.mark.parametrize('command',[['--help'],['check','execute','--help'],['check','status','--run-id','run_'+'a'*32]])
def test_cli_help_and_exact_references_reach_product_parser(tmp_path,command):
    options, forwarded = ENTRY['parse_arguments'](['--var-dir',str(tmp_path),'--cli',*command])
    assert options.cli and options.var_dir == tmp_path and forwarded == command


@pytest.mark.parametrize('mutation',['changed','missing','extra','alias'])
def test_changed_missing_extra_and_noncanonical_members_fail(bundle,mutation):
    if mutation == 'changed':
        (bundle/'runtime/node/node').write_bytes(b'other runtime')
    elif mutation == 'missing':
        (bundle/'app/release.json').unlink()
    elif mutation == 'extra':
        (bundle/'app/unlisted.py').write_bytes(b'')
    else:
        path = bundle/'app/update-manifest.json'
        value = json.loads(path.read_text())
        value['files'][1]['relative_path'] = 'app//release.json'
        path.write_text(json.dumps(value))
    with pytest.raises((ValueError,OSError)):
        VERIFY(bundle)


@pytest.mark.parametrize('member',['runtime/node/node','runtime','start.sh'])
def test_linked_file_directory_and_entry_fail(bundle,member,tmp_path):
    path = bundle/member
    original = bundle.parent/(bundle.name+'-'+member.replace('/','-')+'-original')
    path.rename(original)
    try:
        path.symlink_to(original,target_is_directory=original.is_dir())
    except OSError:
        pytest.skip('当前Windows执行权限未允许创建本地符号链接')
    with pytest.raises((ValueError,OSError)):
        VERIFY(bundle)


pytestmark = [pytest.mark.level2]
