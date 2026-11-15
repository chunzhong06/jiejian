"""原生依赖构建复用受控 Python，保持脚本确认与宿主环境隔离。"""
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from product.backend.infrastructure.runtime.process.controlled import npm
from product.protocols.runtime.node_runtime import NodePackagePlan


@pytest.mark.parametrize('allow_scripts', [False, True])
def test_native_dependency_python_is_explicit_and_only_available_with_scripts(tmp_path, monkeypatch, allow_scripts):
    monkeypatch.setenv('OPENAI_API_KEY', 'private-host-value')
    monkeypatch.setenv('PYTHON', 'untrusted-python')
    monkeypatch.setenv('PROGRAMDATA', str(tmp_path / 'system-program-data'))
    monkeypatch.setenv('USERPROFILE', str(tmp_path / 'private-user'))
    monkeypatch.setenv('npm_config_userconfig', 'private-user-configuration')
    node = tmp_path / 'node/node.exe'
    node.parent.mkdir()
    node.write_bytes(b'controlled node')
    npm_entry = node.parent / 'node_modules/npm/bin/npm-cli.js'
    npm_entry.parent.mkdir(parents=True)
    npm_entry.write_text('', encoding='utf-8')
    root = tmp_path / 'artifact'
    source = root / 'source'
    source.mkdir(parents=True)
    (source / 'package.json').write_text('{"name":"native-example"}', encoding='utf-8')
    (source / 'package-lock.json').write_text('{"lockfileVersion":3,"packages":{}}', encoding='utf-8')
    manifest = SimpleNamespace(package=NodePackagePlan(allow_install_scripts=allow_scripts),
        interpreter_fingerprint='a'*64, instance_id='rti_'+'b'*32)
    observed = []

    def install(_node, _npm, arguments, *, environment, cwd, **_kwargs):
        observed.append(environment)
        if allow_scripts:
            assert environment['PYTHON'] == str(Path(sys.executable).resolve())
            assert environment['PROGRAMDATA'] == str(tmp_path / 'system-program-data')
            assert Path(environment['npm_package_config_node_gyp_devdir']).is_relative_to(tmp_path / 'var')
        else:
            assert 'PYTHON' not in environment and 'PROGRAMDATA' not in environment
        assert 'OPENAI_API_KEY' not in environment
        assert 'USERPROFILE' not in environment
        assert environment['npm_config_userconfig'] == str(root / 'npm-empty.conf')
        assert '--ignore-scripts=' + ('false' if allow_scripts else 'true') in arguments
        (cwd / 'node_modules').mkdir()

    monkeypatch.setattr(npm, '_run', install)
    npm.prepare_dependencies(root, manifest, node, tmp_path / 'var', cancelled=lambda: False)
    assert len(observed) == 1
    assert json.loads((root / 'dependency-state.json').read_text()) == {'stage':'READY', 'cache_reused':False}
