# 验证隔离客户端配置、秘密边界和真实 MCP 协议转交，不改本机正在使用的客户端。
import io
import json
import tomllib
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from product.backend.workflows.agent_access.client_config import dsh_patch, json_patch, toml_patch
from product.backend.workflows.agent_access.connection_files import ConnectionProfile, ConnectionReceipt, protect, unprotect
from product.backend.workflows.agent_access.connections import AgentConnections
from product.backend.workflows.agent_access.connector import relay
from product.backend.workflows.agent_access.service import MCPAccessController, MCP_PAIRING_SECRET_REF
from tests.fixtures.preparation.action_preparation import MemorySecretStore
from tests.fixtures.control_plane import TestClient, create_app, TEST_CONTROL_ORIGIN


ENTRY={'command':'C:/界鉴/runtime/python/python.exe','args':['-B','C:/界鉴/app/product/backend/workflows/agent_access/connector.py','--profile','C:/界鉴/var/runtime/agent.bin']}


def test_dsh_replaces_unmounted_patch_with_insert_and_preserves_js():
    text="- id: unrelated\n  config:\n    key: !!js process.env.OTHER_KEY\n- id: mcp-jiejian\n  name: '@deepseek-ai/dsh-mcp-client'\n  config:\n    serverName: jiejian\n    transport: streamable-http\n    headers:\n      Authorization: !!js process.env.JIEJIAN_MCP_TOKEN\n"
    updated=dsh_patch(text, ENTRY)
    assert 'key: !!js process.env.OTHER_KEY' in updated
    assert 'JIEJIAN_MCP_TOKEN' not in updated
    assert '- insert:' in updated and 'failOnStartupError: false' in updated
    assert 'maxAttempts: 10' in updated
    assert dsh_patch(updated, ENTRY)==updated
    assert len(yaml.compose(updated).value)==2


@pytest.mark.parametrize('client,path',[('codex','.codex/config.toml'),('dsh','.dsh/profiles/desktop/cordis.patch.yml'),('zcode','.zcode/cli/config.json'),('codebuddy','.codebuddy/mcp.json'),('qoder','.qoder/settings.json')])
def test_install_is_private_idempotent_and_reversible(tmp_path,client,path):
    home=tmp_path/'home'; target=home/path;target.parent.mkdir(parents=True)
    before='theme="dark"\n[mcp_servers.other]\ncommand="other"\n' if client=='codex' else '[]\n' if client=='dsh' else '{"mcpServers":{"other":{"command":"other"}},"theme":"dark"}\n'
    target.write_text(before,encoding='utf-8')
    secrets=MemorySecretStore();access=MCPAccessController(TEST_CONTROL_ORIGIN+'/mcp',secrets)
    service=AgentConnections(tmp_path/'var',access,home=home,environ={},protector=lambda x:x,unprotector=lambda x:x)
    first=service.install(client)
    assert first['state']=='AWAITING_CLIENT',first
    if client != 'dsh':
        assert 'DSH' not in first['message']
    token=secrets.read(MCP_PAIRING_SECRET_REF)
    assert token and token not in target.read_text(encoding='utf-8')
    assert token not in json.dumps(first)
    profile=ConnectionProfile.model_validate_json((service.root/(client+'.bin')).read_bytes())
    receipt=service.root/(client+'.activity.json')
    receipt.write_text(ConnectionReceipt(generation=profile.generation,state='TOOLS_READ',tool_count=40,at_us=1).model_dump_json())
    assert service.status(client)['state']=='TOOLS_READ'
    content=target.read_bytes()
    assert service.install(client)['state']=='AWAITING_CLIENT'
    assert target.read_bytes()==content
    assert service.status(client)['state']=='AWAITING_CLIENT'  # 上次连接的回执不属于这次重新连接。
    if client != 'dsh':
        assert 'DSH' not in service.status(client)['message']
    assert service.restore(client)['state']=='NOT_CONFIGURED'
    assert target.read_text(encoding='utf-8')==before


def test_restore_does_not_overwrite_later_client_edits(tmp_path):
    home=tmp_path/'home';target=home/'.qoder/settings.json';target.parent.mkdir(parents=True);target.write_text('{}')
    service=AgentConnections(tmp_path/'var',MCPAccessController(TEST_CONTROL_ORIGIN+'/mcp',MemorySecretStore()),home=home,environ={},protector=lambda x:x,unprotector=lambda x:x)
    service.install('qoder');target.write_text('{"changed":true}')
    assert service.restore('qoder')['code']=='CONFIG_CHANGED'
    assert target.read_text()=='{"changed":true}'


def test_old_dsh_policy_requires_explicit_update_and_reuses_credentials(tmp_path):
    home=tmp_path/'home';target=home/'.dsh/profiles/desktop/cordis.patch.yml';target.parent.mkdir(parents=True)
    store=MemorySecretStore();access=MCPAccessController(TEST_CONTROL_ORIGIN+'/mcp',store)
    service=AgentConnections(tmp_path/'var',access,home=home,environ={},protector=lambda x:x,unprotector=lambda x:x)
    service.install('dsh');token=store.read(MCP_PAIRING_SECRET_REF)
    target.write_text(target.read_text().replace('failOnStartupError: false','failOnStartupError: true'))
    before=target.read_bytes()
    assert service.status('dsh')['code']=='CONFIG_UPDATE_REQUIRED'
    assert target.read_bytes()==before
    assert service.install('dsh')['state']=='AWAITING_CLIENT'
    assert store.read(MCP_PAIRING_SECRET_REF)==token
    assert service.status('dsh')['code']=='NONE'
    assert not access.view().project_grants


def test_zcode_compatible_protocol_update_is_explicit_and_preserves_other_settings(tmp_path):
    home=tmp_path/'home';target=home/'.zcode/cli/config.json';target.parent.mkdir(parents=True)
    target.write_text(json.dumps({'theme':'dark','mcp':{'servers':{'other':{'command':'other','enable':False}}}}))
    store=MemorySecretStore();access=MCPAccessController(TEST_CONTROL_ORIGIN+'/mcp',store)
    service=AgentConnections(tmp_path/'var',access,home=home,environ={},protector=lambda x:x,unprotector=lambda x:x)
    service.install('zcode');token=store.read(MCP_PAIRING_SECRET_REF)
    configured=json.loads(target.read_text())
    assert configured['mcp']['servers']['jiejian']['protocolVersion']=='legacy'
    configured['mcp']['servers']['jiejian']['protocolVersion']='auto'
    target.write_text(json.dumps(configured))
    before=target.read_bytes()
    assert service.status('zcode')['code']=='CONFIG_UPDATE_REQUIRED'
    assert target.read_bytes()==before
    assert service.install('zcode')['state']=='AWAITING_CLIENT'
    updated=json.loads(target.read_text())
    assert updated['mcp']['servers']['jiejian']['protocolVersion']=='legacy'
    assert updated['mcp']['servers']['other']==configured['mcp']['servers']['other']
    assert updated['theme']=='dark'
    assert store.read(MCP_PAIRING_SECRET_REF)==token
    assert not access.view().project_grants


def test_sixth_client_uses_confirmation_link_without_secret(tmp_path):
    store=MemorySecretStore();access=MCPAccessController(TEST_CONTROL_ORIGIN+'/mcp',store)
    service=AgentConnections(tmp_path/'var',access,home=tmp_path,environ={},protector=lambda x:x,unprotector=lambda x:x)
    value=service.install('trae')
    assert value['state']=='AWAITING_CLIENT'
    assert value['open_url'].startswith('trae-cn://trae.ai-ide/mcp-import?')
    assert store.read(MCP_PAIRING_SECRET_REF) not in json.dumps(value)


def test_protected_document_and_loopback_boundary():
    data=b'configuration containing a test credential'
    encrypted=protect(data)
    assert data not in encrypted and unprotect(encrypted)==data
    for endpoint in ['http://example.com/mcp','https://127.0.0.1/mcp','http://user@127.0.0.1:8765/mcp','http://127.0.0.1:8765/mcp?x=1']:
        with pytest.raises(ValidationError):ConnectionProfile(client='dsh',endpoint=endpoint,generation='a'*32)


@pytest.mark.parametrize('protocol',['2025-03-26','2026-07-28'])
def test_stdio_relay_reads_real_server_tools_and_read_only_tool(tmp_path, protocol):
    from mcp_types import PROTOCOL_VERSION_META_KEY, CLIENT_INFO_META_KEY, CLIENT_CAPABILITIES_META_KEY
    store=MemorySecretStore();app=create_app(tmp_path/'var',start_worker=False,secret_store=store,environ={})
    app.state.mcp_access.pair()
    # DSH 通过自动协商选择请求/响应协议；其他客户端仍保留新版显式请求转交。
    profile=ConnectionProfile(client='dsh' if protocol=='2025-03-26' else 'codex',endpoint=TEST_CONTROL_ORIGIN+'/mcp',generation='a'*32)
    info={'name':'isolated-connector-test','version':'1'}
    if protocol=='2025-03-26':
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':protocol,'capabilities':{},'clientInfo':info}}, {'jsonrpc':'2.0','method':'notifications/initialized'}, {'jsonrpc':'2.0','id':2,'method':'tools/list'}, {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'jiejian_project_list','arguments':{}}}]
    else:
        meta={PROTOCOL_VERSION_META_KEY:protocol,CLIENT_INFO_META_KEY:info,CLIENT_CAPABILITIES_META_KEY:{}}
        messages=[{'jsonrpc':'2.0','id':1,'method':'server/discover','params':{'_meta':meta}}, {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{'_meta':meta}}, {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'_meta':meta,'name':'jiejian_project_list','arguments':{}}}]
    source=io.StringIO('\n'.join(json.dumps(item) for item in messages)+'\n');output=io.StringIO();observed=[]
    with TestClient(app) as http:
        relay(profile,source,output,store,http,lambda *args:observed.append(args))
    replies=[json.loads(line) for line in output.getvalue().splitlines()]
    assert len(replies)==3,replies
    assert all('result' in item for item in replies),replies
    assert len(replies[1]['result']['tools'])>=40
    assert any(row[0]=='TOOLS_READ' for row in observed)
    assert store.read(MCP_PAIRING_SECRET_REF) not in output.getvalue()


def test_api_rejects_external_origin_and_unknown_client(tmp_path):
    app=create_app(tmp_path/'var',start_worker=False,secret_store=MemorySecretStore(),environ={})
    with TestClient(app) as http:
        assert http.post('/api/mcp/clients/dsh/connect',json={},headers={'Origin':'http://external.invalid'}).status_code==403
        assert http.post('/api/mcp/clients/unknown/connect',json={}).status_code==422
        assert http.post('/api/mcp/clients/dsh/connect',json={'profile':'../../elsewhere'}).status_code==422


@pytest.mark.parametrize('protocol',['2025-03-26','2026-07-28'])
def test_existing_connector_survives_restart_without_replaying_requests(tmp_path, protocol):
    from collections import Counter
    import httpx
    from mcp_types import PROTOCOL_VERSION_META_KEY, CLIENT_INFO_META_KEY, CLIENT_CAPABILITIES_META_KEY
    from product.backend.workflows.agent_access.service import MCPAccessLevel
    store=MemorySecretStore()
    old=create_app(tmp_path/'old',start_worker=False,secret_store=store,environ={})
    old.state.mcp_access.pair();old.state.mcp_access.set_level('test-project',MCPAccessLevel.EXECUTE)
    new=create_app(tmp_path/'new',start_worker=False,secret_store=store,environ={})
    profiles=[ConnectionProfile(client='codex',endpoint=TEST_CONTROL_ORIGIN+'/mcp',generation=x*32) for x in ['a','b']]
    selected=0;observed=[];calls=Counter();meta={}
    info={'name':'restart-test','version':'1'}
    if protocol=='2025-03-26':
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':protocol,'capabilities':{},'clientInfo':info}},{'jsonrpc':'2.0','method':'notifications/initialized'}]
    else:
        meta={'_meta':{PROTOCOL_VERSION_META_KEY:protocol,CLIENT_INFO_META_KEY:info,CLIENT_CAPABILITIES_META_KEY:{}}}
        messages=[{'jsonrpc':'2.0','id':1,'method':'server/discover','params':meta}]
    messages += [{'jsonrpc':'2.0','id':2,'method':'tools/list','params':meta}]
    messages += [{'jsonrpc':'2.0','id':i,'method':'tools/call','params':{**meta,'name':'jiejian_project_list','arguments':{}}} for i in [3,4,5,6]]
    pending=iter(messages)
    class Source:
        def readline(self, size):
            nonlocal selected
            item=next(pending,None)
            if item is None:return ''
            if item.get('id')==4:selected=1
            if item.get('id')==5:new.state.mcp_access.pause()
            if item.get('id')==6:new.state.mcp_access.resume()
            return json.dumps(item)+'\n'
    with TestClient(old) as first,TestClient(new) as second:
        class HTTP:
            def post(self,url,*,json,headers):
                calls[json.get('id')]+=1
                result=[first,second][selected].post(url,json=json,headers=headers)
                if json.get('id')==3:
                    # 服务可能已经处理业务请求，但响应中断；连接器不得自行再提交一次。
                    raise httpx.ReadError('simulated response loss')
                return result
        output=io.StringIO()
        relay(profiles[0],Source(),output,store,HTTP(),lambda *args:observed.append(args),lambda:profiles[selected])
    replies={item['id']:item for item in map(json.loads,output.getvalue().splitlines())}
    assert 'error' in replies[3] and 'result' in replies[4]
    assert 'error' in replies[5] and 'result' in replies[6]
    assert all(calls[i]==1 for i in [3,4,5,6])
    assert calls['jiejian-resume']==(1 if protocol=='2025-03-26' else 0)
    assert any(row[0]=='REQUEST_ACCEPTED' for row in observed)
    assert not new.state.mcp_access.view().project_grants
    assert store.read(MCP_PAIRING_SECRET_REF) not in output.getvalue()


def test_idle_protocol_recovers_without_business_call_and_respects_pause(tmp_path):
    from product.backend.workflows.agent_access.service import MCPAccessLevel
    store=MemorySecretStore()
    old=create_app(tmp_path/'old',start_worker=False,secret_store=store,environ={})
    old.state.mcp_access.pair();old.state.mcp_access.set_level('project',MCPAccessLevel.EXECUTE)
    new=create_app(tmp_path/'new',start_worker=False,secret_store=store,environ={})
    profiles=[ConnectionProfile(client='dsh',endpoint=TEST_CONTROL_ORIGIN+'/mcp',generation=x*32) for x in ['a','b']]
    selected=0;observed=[];methods=[];step=0
    class Source:
        def readline(self, size):
            nonlocal step,selected
            step+=1
            if step==1:return json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'idle-test','version':'1'}}})+'\n'
            if step==2:return json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n'
            if step==3:
                assert old.state.mcp_access.view().connection_state.value=='CONNECTED'
                selected=1
                return None
            if step==4:
                assert new.state.mcp_access.view().connection_state.value=='CONNECTED'
                assert observed[-1][0]=='CONNECTED'
                assert not new.state.mcp_access.view().project_grants
                new.state.mcp_access.pause()
                return None
            if step==5:
                assert observed[-1][:2]==('FAILED','AUTH_REJECTED')
                new.state.mcp_access.resume()
                return None
            assert observed[-1][0]=='CONNECTED'
            return ''
    with TestClient(old) as first,TestClient(new) as second:
        class HTTP:
            def post(self,url,*,json,headers,**kwargs):
                methods.append(json['method'])
                return [first,second][selected].post(url,json=json,headers=headers)
        output=io.StringIO()
        relay(profiles[0],Source(),output,store,HTTP(),lambda *args:observed.append(args),lambda:profiles[selected])
    assert [item['id'] for item in map(json.loads,output.getvalue().splitlines())]==[1]
    assert methods.count('initialize')==2
    assert methods.count('ping')==3
    assert 'tools/call' not in methods and 'tools/list' not in methods


def test_connector_process_uses_protected_store_with_scrubbed_environment(tmp_path):
    import os
    import socket
    import subprocess
    import sys
    import threading
    import time
    import uvicorn
    from product.backend.api import create_app as production_app
    store=MemorySecretStore()
    sock=socket.socket();sock.bind(('127.0.0.1',0))
    origin=f'http://127.0.0.1:{sock.getsockname()[1]}'
    app=production_app(tmp_path/'runtime',control_origin=origin,control_session_token='isolated-control-'+'x'*44,start_worker=False,secret_store=store,environ={})
    token=app.state.mcp_access.pair().access_token
    profile=tmp_path/'dsh.bin';profile.write_bytes(protect(ConnectionProfile(client='dsh',endpoint=origin+'/mcp',generation='f'*32).model_dump_json().encode()))
    secret=tmp_path/'synthetic-secret.bin';secret.write_bytes(protect(token.encode()))
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='on'))
    thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    try:
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.02)
        assert server.started
        # 替身仅替换受控存储 reader；子进程仍运行正式脚本、DPAPI 文档和真实回环 MCP。
        bootstrap="import sys,runpy;from pathlib import Path;from types import SimpleNamespace;import product.backend.infra.secrets as s;from product.backend.workflows.agent_access.connection_files import unprotect;p=Path(sys.argv[3]);s.default_secret_store=lambda:SimpleNamespace(read=lambda ref:unprotect(p.read_bytes()).decode());sys.argv=[sys.argv[1],'--profile',sys.argv[2]];runpy.run_path(sys.argv[0],run_name='__main__')"
        connector=Path(__file__).resolve().parents[4]/'product/backend/workflows/agent_access/connector.py'
        env={key:value for key,value in os.environ.items() if not any(part in key.upper() for part in ('TOKEN','KEY','PASSWORD','SECRET','DSH_'))}
        messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'isolated-stdio','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
        completed=subprocess.run([sys.executable,'-B','-c',bootstrap,str(connector),str(profile),str(secret)],input='\n'.join(json.dumps(item) for item in messages)+'\n',capture_output=True,text=True,encoding='utf-8',env=env,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert completed.returncode==0,completed.stderr
        replies=[json.loads(line) for line in completed.stdout.splitlines()]
        assert len(replies)==2 and len(replies[1]['result']['tools'])>=40
        assert token not in completed.stdout+completed.stderr
    finally:
        server.should_exit=True;thread.join(10);sock.close()
        secret.unlink(missing_ok=True)
