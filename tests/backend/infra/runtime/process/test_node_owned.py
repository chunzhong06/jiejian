# 真实Windows进程/端口验证：源码漂移、外部监听者和错误端口均不能形成运行对应。
import os
import socket

import httpx
import pytest

from product.backend.core.errors import JiejianError
from product.backend.infra.runtime.process.node_owned import (
    node_reference_matches, start_owned_node,
)
from product.backend.infra.runtime.process.tree import kernel_tree_has_exited
from tests.fixtures.node_runtime import node_runtime_input as _input

pytestmark = pytest.mark.skipif(os.name != 'nt',reason='Windows kernel ownership boundary')


def _free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


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
