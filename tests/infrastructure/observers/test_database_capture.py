"""在真实服务库核对提交与回滚；不以最终值或模拟驱动代替事务事实。"""
from types import SimpleNamespace as NS
from uuid import uuid4
import pytest
from product.protocols.runtime.database_capture import DatabaseCapture,database_secret_name
from product.protocols.runtime.transaction_records import RecordRequestScope
from product.backend.infrastructure.observers.records.database_sql import maintenance_plan,qualified,capture_key
from product.backend.infrastructure.observers.records.database_capture import connection,query,maintain_database,read_database_source,preview_database_maintenance
from product.backend.infrastructure.observers.records.record_facts import request_fact
from product.backend.infrastructure.observers.adapters.json_source import SourceReadError
from tests.support.builders.execution.server_database import local_database

pytestmark=pytest.mark.level4


@pytest.fixture(scope='module',params=['POSTGRESQL','MYSQL'])
def server(request,tmp_path_factory):
    with local_database(request.param,tmp_path_factory.mktemp('server-'+request.param)/'cluster') as value:yield value


@pytest.fixture
def capture(server,tmp_path):
    table='items_'+uuid4().hex[:12]
    spec=DatabaseCapture(connection_id='primary',engine=server.engine,port=server.port,database=server.database,
        namespace=server.namespace,username=server.username,password_env=database_secret_name('fixture-app','primary'),
        table=table,resource_column='id',owner_column='owner',fields=('state',))
    environ={spec.password_env:server.password}
    with connection(spec,environ) as database:
        query(database,'CREATE TABLE '+qualified(spec,table)+'(id varchar(64) PRIMARY KEY,owner varchar(64) NOT NULL,state varchar(64))'+(' ENGINE=InnoDB' if server.engine=='MYSQL' else ''))
        query(database,'INSERT INTO '+qualified(spec,table)+' VALUES(%s,%s,%s)',('resource','owner','closed'));database.commit()
    purpose='INSTALL_DATABASE'
    receipt=maintain_database(tmp_path,'fixture-app',spec,purpose=purpose,
        approved_fingerprint=maintenance_plan(spec,purpose)['fingerprint'],operation_id='ppf_'+uuid4().hex,environ=environ)
    config=NS(database_capture=spec,max_response_bytes=262144)
    scope=RecordRequestScope(scope_id='scope-1',generation=receipt.generation,request_nonce='a'*64,request_digest='b'*64,state='COMPLETE')
    return NS(spec=spec,environ=environ,config=config,scope=scope,root=tmp_path)


def bind(database,capture):
    if capture.spec.engine=='POSTGRESQL':query(database,"SELECT set_config('jiejian.nonce',%s,false)",(capture.scope.request_nonce,))
    else:query(database,'SET @jiejian_nonce=%s,@jiejian_transaction=%s',(capture.scope.request_nonce,uuid4().hex))


@pytest.mark.parametrize('mode,expected',[
    ('commit','CONFIRMED'),('rollback','ABSENT'),('savepoint','ABSENT'),('same_transaction_restore','ABSENT'),
    ('two_commits_restore','CONFIRMED'),('foreign_commit','UNKNOWN'),('open_request','UNKNOWN')])
def test_real_committed_history_and_closed_absence(capture,mode,expected):
    c=capture
    before=read_database_source(c.root,'fixture-app',c.config,'resource',environ=c.environ).snapshot
    with connection(c.spec,c.environ) as database:
        bind(database,c)
        if mode=='savepoint':query(database,'SAVEPOINT point_one')
        if mode=='foreign_commit':
            if c.spec.engine=='POSTGRESQL':query(database,"SELECT set_config('jiejian.nonce','',false)")
            else:query(database,'SET @jiejian_nonce=NULL')
        query(database,'UPDATE '+qualified(c.spec,c.spec.table)+' SET state=%s WHERE id=%s',('open','resource'))
        if mode=='rollback':database.rollback()
        elif mode=='savepoint':query(database,'ROLLBACK TO SAVEPOINT point_one');database.commit()
        elif mode in {'same_transaction_restore','two_commits_restore'}:
            if mode=='two_commits_restore':database.commit();bind(database,c)
            query(database,'UPDATE '+qualified(c.spec,c.spec.table)+' SET state=%s WHERE id=%s',('closed','resource'));database.commit()
        else:database.commit()
    scope=c.scope.model_copy(update={'state':'INCOMPLETE'}) if mode=='open_request' else c.scope
    if mode=='open_request':
        # 该项校验未闭合的无效果窗口；已提交发生仍可形成发生事实。
        before=read_database_source(c.root,'fixture-app',c.config,'resource',environ=c.environ).snapshot
        scope=scope.model_copy(update={'request_nonce':'c'*64})
    view=read_database_source(c.root,'fixture-app',c.config,'resource',scope=scope,verified_subject='member',environ=c.environ)
    fact=request_fact(before,view,path=('state',),expected_state='open',request_nonce=scope.request_nonce,
        request_digest=scope.request_digest,subject_id='member',resource_id='resource',owner_id='owner',collection=c.spec.table)
    assert fact.state==expected


def test_installation_conflict_definition_change_and_exact_remove(capture):
    c=capture
    with pytest.raises(SourceReadError,match='DATABASE_CAPTURE_OBJECT_CONFLICT'):
        maintain_database(c.root,'fixture-app',c.spec,purpose='INSTALL_DATABASE',approved_fingerprint=maintenance_plan(c.spec,'INSTALL_DATABASE')['fingerprint'],operation_id='ppf_'+uuid4().hex,environ=c.environ)
    old_remove=preview_database_maintenance(c.root,'fixture-app',c.spec,'REMOVE_DATABASE')['fingerprint']
    receipt=maintain_database(c.root,'fixture-app',c.spec,purpose='REMOVE_DATABASE',approved_fingerprint=old_remove,operation_id='ppf_'+uuid4().hex,environ=c.environ)
    assert receipt.state=='REMOVED'
    with pytest.raises(SourceReadError,match='DATABASE_CAPTURE_NOT_INSTALLED'):
        read_database_source(c.root,'fixture-app',c.config,'resource',environ=c.environ)
    with connection(c.spec,c.environ) as database:
        assert query(database,'SELECT state FROM '+qualified(c.spec,c.spec.table))[0]['state']=='closed'
    maintain_database(c.root,'fixture-app',c.spec,purpose='INSTALL_DATABASE',approved_fingerprint=maintenance_plan(c.spec,'INSTALL_DATABASE')['fingerprint'],operation_id='ppf_'+uuid4().hex,environ=c.environ)
    assert preview_database_maintenance(c.root,'fixture-app',c.spec,'REMOVE_DATABASE')['fingerprint']!=old_remove
    with pytest.raises(SourceReadError):
        maintain_database(c.root,'fixture-app',c.spec,purpose='REMOVE_DATABASE',approved_fingerprint=old_remove,operation_id='ppf_'+uuid4().hex,environ=c.environ)
    assert read_database_source(c.root,'fixture-app',c.config,'resource',environ=c.environ).snapshot.data['state']=='closed'


def test_ordinary_node_pool_correlates_each_request_and_unfinished_transaction(capture,tmp_path):
    import hashlib,json,os,shutil,time
    from pathlib import Path
    import httpx
    from product.protocols.runtime.node_runtime import NodeRuntimeManifest,NodeRuntimeLoadRequest,NodePackagePlan,node_document_fingerprint
    from product.protocols.runtime.runtime_identity import RuntimeFile,runtime_source_fingerprint
    from product.backend.infrastructure.runtime.process.controlled.artifact import create_node_runtime_artifact
    from product.backend.infrastructure.runtime.process.controlled.node_owned import start_owned_node,node_execution_identity,node_artifact_store
    from tests.support.builders.runtime.node_runtime import free_port
    if os.name!='nt':pytest.skip('需要 Windows 受控 Node 运行')
    c=capture
    repository=Path(__file__).resolve().parents[3]
    node=Path(json.loads((repository/'var/runtime/source/receipt.json').read_text(encoding='utf-8-sig'))['node']['executable'])
    source=tmp_path/'source';source.mkdir()
    for name in ('package.json','package-lock.json'):shutil.copyfile(repository/'tests/fixtures/database-node'/name,source/name)
    pg=c.spec.engine=='POSTGRESQL'
    config=dict(host=c.spec.host,port=c.spec.port,database=c.spec.database,user=c.spec.username,max=1,connectionLimit=1)
    setup=("const {Pool}=require('pg');const pool=new Pool(config);const acquire=()=>pool.connect();" if pg else
        "const mysql=require('mysql2/promise');const pool=mysql.createPool(config);const acquire=()=>pool.getConnection();")
    script="const http=require('node:http');const config="+json.dumps(config)+";config.password=process.env["+json.dumps(c.spec.password_env)+"];"+setup+"""
      let held;
      http.createServer(async(req,res)=>{
        let client;
        try {
          client=await acquire();
          if(req.url==='/pending'){await client.query('BEGIN');held=client;}
          if(req.url==='/rollback'||req.url==='/savepoint')await client.query('BEGIN');
          if(req.url==='/savepoint')await client.query('SAVEPOINT point_one');
          if(req.url!=='/noop')await client.query(UPDATE_SQL,['open','resource']);
          if(req.url==='/rollback')await client.query('ROLLBACK');
          if(req.url==='/savepoint'){await client.query('ROLLBACK TO SAVEPOINT point_one');await client.query('COMMIT');}
          if(req.url!=='/pending')await client.release();
          res.end('ready');
        }catch(error){res.statusCode=500;res.end(String(error.code??'DATABASE_TEST_FAILED'));}
      }).listen(Number(process.env.PORT),'127.0.0.1');
    """
    update='UPDATE '+qualified(c.spec,c.spec.table)+' SET state='+('$1' if pg else '?')+' WHERE id='+('$2' if pg else '?')
    script=script.replace('UPDATE_SQL',json.dumps(update))
    (source/'app.cjs').write_text(script,encoding='utf-8')
    files=tuple(RuntimeFile(relative_path=file.name,size=file.stat().st_size,sha256=hashlib.sha256(file.read_bytes()).hexdigest()) for file in sorted(source.iterdir()))
    manifest=NodeRuntimeManifest(instance_id='rti_'+uuid4().hex,project_id='fixture-app',entry='app.cjs',port=free_port(),
        files=files,source_fingerprint=runtime_source_fingerprint(files),**node_execution_identity(node),module_loader='NODE_STANDARD',package=NodePackagePlan(),databases=(c.spec,))
    create_node_runtime_artifact(source,node_artifact_store(c.root),manifest=manifest)
    request=NodeRuntimeLoadRequest(load_id='rld_'+uuid4().hex,project_id='fixture-app',operation_id=uuid4().hex,control_session_id='rcs_'+'4'*32,
        preview_fingerprint='c'*64,instance_id=manifest.instance_id,manifest_fingerprint=node_document_fingerprint(manifest),source_fingerprint=manifest.source_fingerprint,created_at_us=time.time_ns()//1000)
    owned=start_owned_node(c.root,request,node,environ=dict(os.environ)|c.environ,timeout=15)
    try:
        with httpx.Client(trust_env=False,timeout=5) as client:
            for route,expected,completion in [('/noop','ABSENT','COMPLETE'),('/commit','CONFIRMED','COMPLETE'),('/rollback','ABSENT','COMPLETE'),('/savepoint','ABSENT','COMPLETE'),('/pending','UNKNOWN','INCOMPLETE')]:
                before=read_database_source(c.root,'fixture-app',c.config,'resource',environ=c.environ).snapshot
                nonce=uuid4().hex+uuid4().hex
                response=client.get(f'http://127.0.0.1:{manifest.port}'+route,headers={'X-Jiejian-Request-Nonce':nonce})
                assert response.status_code==200,response.text
                scope=owned.record_server.store.request_scope(nonce)
                assert scope.state==completion
                view=read_database_source(c.root,'fixture-app',c.config,'resource',scope=scope,verified_subject='member',environ=c.environ)
                fact=request_fact(before,view,path=('state',),expected_state='open',request_nonce=nonce,
                    request_digest=hashlib.sha256(('GET\n'+route).encode()).hexdigest(),subject_id='member',resource_id='resource',owner_id='owner',collection=c.spec.table)
                assert fact.state==expected
    finally:owned.stop()


def test_interrupted_installation_only_removes_confirmed_owned_objects(capture,tmp_path):
    from product.backend.infrastructure.observers.records.database_capture import read_database_receipt,read_installation
    c=capture
    spec=c.spec.model_copy(update={'connection_id':'partial','password_env':database_secret_name('fixture-app','partial')})
    environment={spec.password_env:next(iter(c.environ.values()))}
    operation='ppf_'+uuid4().hex
    calls=[]
    def interrupted():
        calls.append(True)
        return len(calls)>=4
    with pytest.raises(SourceReadError,match='DATABASE_MAINTENANCE_INTERRUPTED'):
        maintain_database(tmp_path,'fixture-app',spec,purpose='INSTALL_DATABASE',approved_fingerprint=maintenance_plan(spec,'INSTALL_DATABASE')['fingerprint'],
            operation_id=operation,environ=environment,cancelled=interrupted)
    receipt=read_database_receipt(tmp_path,'fixture-app',spec)
    assert receipt.state=='INCOMPLETE'
    assert len(receipt.definitions)==(2 if spec.engine=='MYSQL' else 0)
    assert read_installation(tmp_path,'fixture-app',spec) is None
    with pytest.raises(SourceReadError,match='DATABASE_MAINTENANCE_RECEIPT_UNKNOWN'):
        maintain_database(tmp_path,'fixture-app',spec,purpose='INSTALL_DATABASE',approved_fingerprint=maintenance_plan(spec,'INSTALL_DATABASE')['fingerprint'],operation_id=operation,environ=environment)
    removed=maintain_database(tmp_path,'fixture-app',spec,purpose='REMOVE_DATABASE',approved_fingerprint=preview_database_maintenance(tmp_path,'fixture-app',spec,'REMOVE_DATABASE')['fingerprint'],operation_id='ppf_'+uuid4().hex,environ=environment)
    assert removed.state=='REMOVED' and not removed.definitions
