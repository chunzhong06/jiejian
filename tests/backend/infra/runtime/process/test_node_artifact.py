# 真实 Node 子进程验证冻结模块范围与失败关闭；不将加载器测试当作运行对应或版本验收。
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from product.backend.infra.runtime.process.controlled.artifact import create_node_runtime_artifact, verify_runtime_artifact
from product.protocols.runtime.node_runtime import NodeRuntimeManifest
from product.protocols.runtime.runtime_identity import RuntimeFile, runtime_source_fingerprint

ROOT = Path(__file__).resolve().parents[5]
EXECUTOR = ROOT / 'product/backend/infra/runtime/process/controlled/node_target.mjs'


def _artifact(tmp_path, modules):
    source = tmp_path / 'source'
    source.mkdir()
    files = []
    for name, text in sorted(modules.items(), key=lambda item: (item[0].casefold(), item[0])):
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = text.encode('utf-8')
        target.write_bytes(raw)
        files.append(RuntimeFile(relative_path=name, size=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    node = Path(json.loads((ROOT / 'var/runtime/source/receipt.json').read_text(encoding='utf-8-sig'))['node']['executable'])
    with node.open('rb') as stream:
        interpreter_fingerprint = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = NodeRuntimeManifest(instance_id='rti_' + uuid4().hex, project_id='app_' + 'a' * 32,
        entry='app.mjs', port=19273, files=tuple(files), source_fingerprint=runtime_source_fingerprint(tuple(files)),
        interpreter_fingerprint=interpreter_fingerprint,
        executor_fingerprint=hashlib.sha256(EXECUTOR.read_bytes()).hexdigest())
    artifact = create_node_runtime_artifact(source, tmp_path / 'artifacts', manifest=manifest)
    raw_hash = hashlib.sha256((artifact / 'launch.json').read_bytes()).hexdigest()
    (artifact / 'start.gate').write_text(raw_hash, encoding='ascii')
    data = tmp_path / 'data'
    data.mkdir()
    command = [str(node), '--experimental-vm-modules', '--permission', f'--allow-fs-read={artifact}',
        f'--allow-fs-read={EXECUTOR}', f'--allow-fs-read={data}', f'--allow-fs-write={data}',
        str(EXECUTOR), str(artifact / 'launch.json'), raw_hash, str(data)]
    return artifact, data, command, manifest


def _execute(command, data):
    # 不继承 NODE_OPTIONS、NODE_PATH 或客户端秘密；目标不获得源码副本的写权限。
    environment = {key: value for key, value in os.environ.items() if key.upper() in {'SYSTEMROOT', 'WINDIR'}}
    return subprocess.run(command, cwd=data, env=environment, capture_output=True, timeout=10, check=False)


def test_node_static_relative_modules_execute_only_frozen_bytes(tmp_path):
    artifact, data, command, manifest = _artifact(tmp_path, {
        'app.mjs': "import fs from 'node:fs'; import {value} from './lib/value.mjs'; fs.writeFileSync(process.env.JIEJIAN_DATA_DIR+'/result.json',JSON.stringify(value));",
        'lib/value.mjs': "export const value={status:'当前冻结内容'};",
    })
    result = _execute(command, data)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert json.loads((data / 'result.json').read_text(encoding='utf-8')) == {'status':'当前冻结内容'}
    verify_runtime_artifact(artifact / 'source', manifest)


@pytest.mark.parametrize('script', [
    "import 'external-package';",
    "import '/outside.mjs';",
    "await import('./module.mjs');",
    "import http from 'node:http'; http.createServer().listen(0,'127.0.0.1'); await import('./module.mjs');",
    "import {spawn} from 'node:child_process'; spawn('unused');",
    "eval('1+1');",
    "import fs from 'node:fs'; fs.writeFileSync(new URL('./app.mjs', import.meta.url),'changed');",
])
def test_node_unsupported_loading_and_artifact_write_are_rejected(tmp_path, script):
    _, data, command, _ = _artifact(tmp_path, {'app.mjs':script, 'module.mjs':'export default 1;'})
    result = _execute(command, data)
    assert result.returncode != 0
    assert result.stdout == b''


def test_node_changed_source_or_gate_cannot_execute(tmp_path):
    artifact, data, command, _ = _artifact(tmp_path, {'app.mjs':"import fs from 'node:fs'; fs.writeFileSync(process.env.JIEJIAN_DATA_DIR+'/executed','yes');"})
    (artifact / 'start.gate').write_text('0' * 64, encoding='ascii')
    assert _execute(command, data).returncode != 0
    assert not (data / 'executed').exists()
    (artifact / 'start.gate').write_text(command[-2], encoding='ascii')
    (artifact / 'source/app.mjs').write_text('throw 1;', encoding='utf-8')
    assert _execute(command, data).returncode != 0
    assert not (data / 'executed').exists()
