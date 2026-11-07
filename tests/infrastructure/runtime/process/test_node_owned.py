# 真实Windows进程/端口验证：源码漂移、外部监听者和错误端口均不能形成运行对应。
import os
import socket

import httpx
import pytest

from product.backend.domain.errors import JiejianError
from product.backend.infrastructure.runtime.process.controlled.node_owned import node_reference_matches, start_owned_node
from product.backend.infrastructure.runtime.process.tree import kernel_tree_has_exited
from tests.support.builders.runtime.node_runtime import free_port as _free_port, node_runtime_input as _input

pytestmark = [pytest.mark.level4, pytest.mark.skipif(os.name != 'nt', reason='Windows kernel ownership boundary')]




def test_owned_node_matches_only_its_frozen_source_and_live_listener(tmp_path):
    port=_free_port();node,artifact,request=_input(tmp_path,port)
    owned=start_owned_node(tmp_path/'var',request,node,environ=dict(os.environ))
    try:
        assert node_reference_matches(tmp_path/'var',request,owned.reference,node)
        with httpx.Client(trust_env=False) as client:
            assert client.get(f'http://127.0.0.1:{port}').text=='frozen source'
        (artifact/'source/app.mjs').write_text('// changed',encoding='utf-8')
        assert not node_reference_matches(tmp_path/'var',request,owned.reference,node)
    finally: owned.stop()
    assert not node_reference_matches(tmp_path/'var',request,owned.reference,node)
    assert kernel_tree_has_exited({'kind':'windows-job','name':'jiejian-node-'+request.instance_id})


def test_external_listener_is_neither_adopted_nor_stopped(tmp_path):
    with socket.socket() as external:
        external.bind(('127.0.0.1',0));external.listen()
        port=external.getsockname()[1]
        node,artifact,request=_input(tmp_path,port)
        with pytest.raises(JiejianError): start_owned_node(tmp_path/'var',request,node,environ=dict(os.environ))
        assert not (artifact/'start.gate').exists()
        with socket.create_connection(('127.0.0.1',port),timeout=1): pass


def test_wrong_listening_port_fails_and_cleans_owned_process_tree(tmp_path):
    node,_,request=_input(tmp_path,_free_port(),wrong_port=True)
    with pytest.raises(JiejianError): start_owned_node(tmp_path/'var',request,node,environ=dict(os.environ),timeout=.5)
    assert kernel_tree_has_exited({'kind':'windows-job','name':'jiejian-node-'+request.instance_id})


def test_standard_commonjs_build_runs_frozen_output_and_detects_output_drift(tmp_path):
    import hashlib,json,time
    from pathlib import Path
    from uuid import uuid4
    from product.protocols.runtime.node_runtime import NodeRuntimeManifest,NodeRuntimeLoadRequest,NodePackagePlan,node_document_fingerprint
    from product.protocols.runtime.runtime_identity import RuntimeFile,runtime_source_fingerprint
    from product.backend.infrastructure.runtime.process.controlled.artifact import create_node_runtime_artifact
    from product.backend.infrastructure.runtime.process.controlled.node_owned import node_artifact_store,node_execution_identity
    root=Path(__file__).resolve().parents[4]
    node=Path(json.loads((root/'var/runtime/source/receipt.json').read_text(encoding='utf-8-sig'))['node']['executable'])
    source=tmp_path/'source';source.mkdir()
    inputs={
        'package.json':json.dumps(dict(name='independent-build',version='1.0.0',scripts={'build':'node build.cjs'})),
        'package-lock.json':json.dumps(dict(name='independent-build',version='1.0.0',lockfileVersion=3,packages={'':dict(name='independent-build',version='1.0.0')})),
        'build.cjs':"const fs=require('node:fs');fs.mkdirSync('dist');fs.copyFileSync('server.cjs','dist/server.cjs');",
        'server.cjs':"require('node:http').createServer((req,res)=>res.end('built CommonJS')).listen(Number(process.env.PORT),'127.0.0.1');"}
    files=[]
    for name,content in sorted(inputs.items()):
        raw=content.encode();(source/name).write_bytes(raw)
        files.append(RuntimeFile(relative_path=name,size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
    manifest=NodeRuntimeManifest(instance_id='rti_'+uuid4().hex,project_id='app_'+'b'*32,entry='dist/server.cjs',port=_free_port(),
        files=tuple(files),source_fingerprint=runtime_source_fingerprint(tuple(files)),**node_execution_identity(node),module_loader='NODE_STANDARD',package=NodePackagePlan(build_script='build'))
    var=tmp_path/'var';artifact=create_node_runtime_artifact(source,node_artifact_store(var),manifest=manifest)
    request=NodeRuntimeLoadRequest(load_id='rld_'+uuid4().hex,project_id=manifest.project_id,operation_id=uuid4().hex,control_session_id='rcs_'+'4'*32,
        preview_fingerprint='c'*64,instance_id=manifest.instance_id,manifest_fingerprint=node_document_fingerprint(manifest),source_fingerprint=manifest.source_fingerprint,created_at_us=time.time_ns()//1000)
    owned=start_owned_node(var,request,node,environ=dict(os.environ))
    try:
        with httpx.Client(trust_env=False) as client:assert client.get(f'http://127.0.0.1:{manifest.port}').text=='built CommonJS'
        assert not (source/'dist').exists()
        assert node_reference_matches(var,request,owned.reference,node)
        (artifact/'source/dist/server.cjs').write_text('changed output',encoding='utf-8')
        assert not node_reference_matches(var,request,owned.reference,node)
    finally:owned.stop()
