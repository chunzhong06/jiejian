# 用最小协议驱动验证真实 Node 请求与独立记录组件；不引入某个业务应用的专用信任。
import hashlib
import os
import secrets

import httpx
import pytest

from product.backend.infra.runtime.process.node_owned import start_owned_node
from product.backend.infra.observers.record_facts import request_fact
from tests.fixtures.node_runtime import node_runtime_input, free_port

pytestmark = pytest.mark.skipif(os.name != 'nt',reason='Windows owned runtime')

DRIVER = """
import http from 'node:http';
import {openCollection} from 'jiejian:records';
const records=openCollection('units');
await records.seed('one','principal-a',{phase:'initial'});
http.createServer(async (req,res)=>{
  const item=await records.read('one');
  const input={resource_id:'one',subject_id:'principal-b',expected_version:item.version,
    changes:[{path:['phase'],value:'protected'},{path:['phase'],value:'initial'}]};
  if(req.url==='/change') await records.transact(input);
  if(req.url==='/unawaited') records.transact(input).catch(()=>{});
  if(req.url==='/late') setTimeout(()=>records.transact(input).catch(()=>{}),10);
  res.writeHead(403,{'Content-Type':'application/json'});res.end('{"error":"denied"}');
}).listen(Number(process.env.PORT),'127.0.0.1');
"""


@pytest.mark.parametrize('route,expected,completion',[
    ('/deny','ABSENT','COMPLETE'),('/change','CONFIRMED','COMPLETE'),
    ('/unawaited','UNKNOWN','INCOMPLETE'),('/late','ABSENT','COMPLETE')])
def test_request_completion_is_owned_and_publish_restore_is_not_erased(tmp_path,route,expected,completion):
    port=free_port()
    node,_,request=node_runtime_input(tmp_path,port,script=DRIVER)
    owned=start_owned_node(tmp_path/'var',request,node,environ=dict(os.environ))
    try:
        store=owned.record_server.store
        before=store.read('units','one')
        nonce=secrets.token_hex(32)
        with httpx.Client(trust_env=False) as client:
            response=client.get(f'http://127.0.0.1:{port}{route}',headers={'X-Jiejian-Request-Nonce':nonce})
        assert response.status_code==403
        view=store.proof_view('units','one',request_nonce=nonce)
        assert view.scope.state==completion
        fact=request_fact(before,view,path=('phase',),expected_state='protected',request_nonce=nonce,
            request_digest=hashlib.sha256(('GET\n'+route).encode()).hexdigest(),subject_id='principal-b',
            resource_id='one',owner_id='principal-a',collection='units')
        # 未等待的请求可能先提交，也可能被关闭边界拒绝；两者都不能误报“未发生”。
        assert fact.state in ({'UNKNOWN','CONFIRMED'} if route=='/unawaited' else {expected})
        if route=='/change':
            assert view.snapshot.data['phase']=='initial'
            assert len(view.operations[0].transitions)==2
        with pytest.raises(OSError):
            with store.database.open('r+b'):
                pass
    finally:
        owned.stop()
