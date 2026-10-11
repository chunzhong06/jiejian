# 验证 DSH 展示格式适配不改变调用时的原始参数约束。
import io
import json

import httpx
import pytest
from product.backend.workflows.agent_access.dsh_schema import DshSchemaError, DshToolSchemas, project_schema
from product.backend.workflows.agent_access.connector import relay
from product.backend.workflows.agent_access.connection_files import ConnectionProfile
from tests.fixtures.preparation.action_preparation import MemorySecretStore


SCHEMA = {'type':'object', 'properties': {
    'operation_id': {'type':'string','pattern':'^op_[a-z]+$','minLength':5},
    'note': {'anyOf':[{'type':'string'},{'type':'null'}]},
    'mode': {'$ref':'#/$defs/Mode'},
}, 'required':['operation_id','mode'], 'additionalProperties':False,
    '$defs':{'Mode':{'type':'string','enum':['READ','PREPARE']}}}


def test_projection_preserves_structure_and_full_runtime_validation():
    adapter=DshToolSchemas()
    projected=adapter.adapt({'result':{'tools':[{'name':'save','inputSchema':SCHEMA}]}})['result']['tools'][0]['inputSchema']
    assert projected['properties']['note']['oneOf']==[{'type':'string'},{'type':'null'}]
    assert projected['properties']['mode']['enum']==['READ','PREPARE']
    assert 'pattern' in projected['properties']['operation_id']['description']
    assert adapter.validate('save',{'operation_id':'op_good','mode':'READ','note':None})
    for invalid in [ {'operation_id':'bad','mode':'READ'}, {'operation_id':'op_a','mode':'READ'},
                     {'operation_id':'op_good','mode':'EXECUTE'}, {'operation_id':'op_good','mode':'READ','extra':True},
                     {'operation_id':'op_good'}, {'operation_id':'op_good','mode':'READ','note':False} ]:
        assert not adapter.validate('save',invalid)
    assert not adapter.validate('unknown',{})
    assert 'pattern' in SCHEMA['properties']['operation_id']


@pytest.mark.parametrize('schema',[
    {'anyOf':[{'type':'integer'},{'type':'number'}]},
    {'$ref':'https://example.invalid/schema'},
    {'$ref':'#/$defs/Loop','$defs':{'Loop':{'$ref':'#/$defs/Loop'}}},
    {'type':'object','unevaluatedProperties':False},
])
def test_unsupported_shapes_fail_closed(schema):
    with pytest.raises(DshSchemaError):project_schema(schema)


def test_dsh_negotiation_declines_streaming_era_without_hitting_http():
    from product.backend.workflows.agent_access.service import MCP_PAIRING_SECRET_REF
    store=MemorySecretStore();store.write(MCP_PAIRING_SECRET_REF,'synthetic')
    output=io.StringIO();observed=[]
    with httpx.Client(transport=httpx.MockTransport(lambda request:pytest.fail('discovery must not advertise an unsupported SSE transport'))) as http:
        relay(ConnectionProfile(client='dsh',endpoint='http://127.0.0.1:8765/mcp',generation='f'*32),
              io.StringIO(json.dumps({'jsonrpc':'2.0','id':1,'method':'server/discover'})+'\n'),output,store,http,lambda *v:observed.append(v))
    assert json.loads(output.getvalue())['error']['code']==-32601


def test_invalid_dsh_arguments_never_reach_the_business_request():
    from product.backend.workflows.agent_access.service import MCP_PAIRING_SECRET_REF
    store=MemorySecretStore();store.write(MCP_PAIRING_SECRET_REF,'synthetic')
    methods=[]
    def respond(request):
        value=json.loads(request.content);methods.append(value['method'])
        assert value['method']=='tools/list'
        return httpx.Response(200,json={'jsonrpc':'2.0','id':value['id'],'result':{'tools':[{'name':'save','inputSchema':SCHEMA}]}})
    output=io.StringIO()
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        relay(ConnectionProfile(client='dsh',endpoint='http://127.0.0.1:8765/mcp',generation='f'*32),
              io.StringIO(json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'save','arguments':{'operation_id':'bad','mode':'READ'}}})+'\n'),output,store,http,lambda *v:None)
    assert methods==['tools/list']
    assert json.loads(output.getvalue())['error']['code']==-32602
    assert 'arguments.operation_id' in output.getvalue()
    assert 'bad' not in output.getvalue()


def test_dsh_field_errors_never_echo_unknown_names_or_values():
    adapter=DshToolSchemas()
    adapter.adapt({'result':{'tools':[{'name':'save','inputSchema':SCHEMA}]}})
    issues=adapter.validation_issues('save',{'operation_id':'private value','mode':'READ','private-key':'private-secret'})
    text=json.dumps(issues)
    assert 'arguments.operation_id' in text
    assert not any(value in text for value in ('private value','private-key','private-secret'))
    assert adapter.validation_issues('save',{'operation_id':'op_good','mode':'READ'})==[]


@pytest.mark.parametrize('error,code',[(httpx.ConnectTimeout,'CONNECT_TIMEOUT'),(httpx.ReadTimeout,'RESPONSE_TIMEOUT'),(httpx.ConnectError,'SERVICE_UNAVAILABLE')])
def test_transport_failure_records_the_specific_stage_without_retry(error,code):
    from product.backend.workflows.agent_access.service import MCP_PAIRING_SECRET_REF
    store=MemorySecretStore();store.write(MCP_PAIRING_SECRET_REF,'synthetic')
    methods=[];observed=[];phases=[]
    def fail(request):
        methods.append(json.loads(request.content)['method'])
        raise error('synthetic private transport detail',request=request)
    output=io.StringIO()
    with httpx.Client(transport=httpx.MockTransport(fail)) as http:
        relay(ConnectionProfile(client='dsh',endpoint='http://127.0.0.1:8765/mcp',generation='f'*32),
              io.StringIO(json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}})+'\n'),
              output,store,http,lambda *v:observed.append(v),diagnose=phases.append)
    assert methods==['initialize'] and phases==['INITIALIZE']
    assert ('FAILED',code,0) in observed
    assert 'synthetic' not in output.getvalue()


def test_dsh_patch_preserves_custom_retry_and_unrelated_configuration():
    import yaml
    from product.backend.workflows.agent_access.client_config import dsh_patch
    entry = {'command':'C:/界鉴/runtime/python/python.exe', 'args':['-B','C:/界鉴/app/connector.py','--profile','C:/界鉴/var/runtime/agent.bin']}
    text=yaml.safe_dump([{'id':'other','config':{'enabled':True}}, {'insert':[{'id':'mcp-jiejian','name':'@deepseek-ai/dsh-mcp-client','config':{
        **entry,'serverName':'jiejian','transport':'stdio','failOnStartupError':True,'toolCallTimeoutMs':45000,
        'reconnect':{'enabled':True,'initialDelayMs':750,'maxDelayMs':20000,'maxAttempts':6}}}]}],sort_keys=False)
    result=yaml.safe_load(dsh_patch(text,entry))
    assert result[0]==yaml.safe_load(text)[0]
    config=result[1]['insert'][0]['config']
    assert config['toolCallTimeoutMs']==45000 and config['reconnect']=={'enabled':True,'initialDelayMs':750,'maxDelayMs':20000,'maxAttempts':6}
    assert config['failOnStartupError'] is False
