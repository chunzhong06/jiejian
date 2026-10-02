# 构造隔离Node源码、冻结清单与加载输入；不启动进程、不生成通过结论。
import hashlib
import json
from pathlib import Path
import time
import socket
from uuid import uuid4

from product.backend.infra.runtime.process.artifact import create_node_runtime_artifact
from product.backend.infra.runtime.process.node_owned import EXECUTOR, node_artifact_store
from product.protocols.node_runtime import NodeRuntimeManifest, NodeRuntimeLoadRequest, node_document_fingerprint
from product.protocols.runtime_identity import RuntimeFile, runtime_source_fingerprint

ROOT=Path(__file__).resolve().parents[2]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def node_runtime_input(tmp_path, port, *, wrong_port=False, control_session_id=None, script=None):
    node=Path(json.loads((ROOT/'var/runtime/source/receipt.json').read_text(encoding='utf-8-sig'))['node']['executable'])
    source=tmp_path/'source';source.mkdir()
    script=script or "import http from 'node:http'; http.createServer((req,res)=>res.end('frozen source')).listen("+('0' if wrong_port else 'Number(process.env.PORT)')+",'127.0.0.1');"
    raw=script.encode();(source/'app.mjs').write_bytes(raw)
    files=(RuntimeFile(relative_path='app.mjs',sha256=hashlib.sha256(raw).hexdigest(),size=len(raw)),)
    with node.open('rb') as stream: interpreter=hashlib.file_digest(stream,'sha256').hexdigest()
    manifest=NodeRuntimeManifest(instance_id='rti_'+uuid4().hex,project_id='owned-node-project',entry='app.mjs',
        port=port,files=files,source_fingerprint=runtime_source_fingerprint(files),interpreter_fingerprint=interpreter,
        executor_fingerprint=hashlib.sha256(EXECUTOR.read_bytes()).hexdigest())
    artifact=create_node_runtime_artifact(source,node_artifact_store(tmp_path/'var'),manifest=manifest)
    request=NodeRuntimeLoadRequest(load_id='rld_'+uuid4().hex,project_id=manifest.project_id,operation_id=uuid4().hex,
        control_session_id=control_session_id or 'rcs_'+'4'*32,
        preview_fingerprint='c'*64,
        instance_id=manifest.instance_id,manifest_fingerprint=node_document_fingerprint(manifest),
        source_fingerprint=manifest.source_fingerprint,created_at_us=time.time_ns()//1000)
    return node,artifact,request
