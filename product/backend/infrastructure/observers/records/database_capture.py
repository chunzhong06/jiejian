"""仅由 Worker/Runner 调用的服务库安装和只读提交历史；不输出驱动异常或凭据。"""
from collections import OrderedDict
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
from uuid import uuid4
from product.backend.infrastructure.observers.adapters.json_source import SourceReadError
from product.backend.infrastructure.observers.records.database_sql import capture_key,qualified,quote,statements,maintenance_plan
from product.protocols.runtime.database_installation import DatabaseInstallation
from product.protocols.runtime.transaction_records import RecordSnapshot,RecordOperation,RecordTransition,RecordProofView


@contextmanager
def connection(spec,environ,*,readonly=False):
    password=environ.get(spec.password_env)
    if not password:
        raise SourceReadError('DATABASE_CREDENTIAL_UNAVAILABLE')
    if spec.engine=='POSTGRESQL':
        import psycopg
        driver_errors=(psycopg.Error,OSError)
    else:
        import pymysql
        driver_errors=(pymysql.MySQLError,OSError)
    database=None
    failed=False
    try:
        if spec.engine=='POSTGRESQL':
            database=psycopg.connect(host=spec.host,port=spec.port,dbname=spec.database,user=spec.username,
                password=password,connect_timeout=3,options='-c statement_timeout=3000 -c lock_timeout=1000',autocommit=False)
            if readonly:database.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        else:
            database=pymysql.connect(host=spec.host,port=spec.port,database=spec.database,user=spec.username,
                password=password,connect_timeout=3,read_timeout=3,write_timeout=3,autocommit=False,charset='utf8mb4')
            if readonly:
                with database.cursor() as cursor:cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        try:
            yield database
        except BaseException:
            failed=True
            raise
    except driver_errors:
        # 仅驱动和连接错误脱敏；调用者的契约错误不能伪装成数据库不可用。
        raise SourceReadError('DATABASE_OPERATION_UNAVAILABLE') from None
    finally:
        if database is not None:
            try:
                try:database.rollback()
                finally:database.close()
            except driver_errors:
                if not failed:raise SourceReadError('DATABASE_OPERATION_UNAVAILABLE') from None


def query(database,sql,args=()):
    with database.cursor() as cursor:
        cursor.execute(sql,args)
        if cursor.description is None:return []
        names=tuple(item[0] for item in cursor.description)
        values=cursor.fetchmany(4097)
        if len(values)>4096:raise SourceReadError('DATABASE_HISTORY_LIMIT')
        return [dict(zip(names,row)) for row in values]


def installation_path(var_dir,project_id,spec):
    root=Path(var_dir).resolve()/'runtime/database-installations'/project_id
    return root/(capture_key(spec)+'.json')


def read_database_receipt(var_dir,project_id,spec):
    path=installation_path(var_dir,project_id,spec)
    try:
        if path.resolve()!=path or path.is_symlink() or path.stat().st_size>16384:
            return None
        value=DatabaseInstallation.model_validate_json(path.read_bytes())
        return value if value.project_id==project_id and value.capture==spec else None
    except (OSError,ValueError):return None


def read_installation(var_dir,project_id,spec):
    value=read_database_receipt(var_dir,project_id,spec)
    return value if value is not None and value.state=='INSTALLED' else None


def save_database_receipt(path,receipt):
    temporary=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    with temporary.open('x',encoding='utf-8') as stream:
        stream.write(receipt.model_dump_json());stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def definitions(database,spec):
    prefix=capture_key(spec)
    if spec.engine=='POSTGRESQL':
        records=query(database,"""SELECT c.relname AS name, c.relkind::text AS kind,c.relrowsecurity,c.relforcerowsecurity,
            (SELECT string_agg(pg_get_constraintdef(k.oid),',' ORDER BY k.conname) FROM pg_constraint k WHERE k.conrelid=c.oid) AS constraints,
            (SELECT string_agg(a.attname||':'||a.atttypid::text||':'||a.attnotnull::text,',' ORDER BY a.attnum)
             FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped) AS definition
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND c.relname IN (%s,%s,%s)""",(spec.namespace,prefix+'_meta',prefix+'_versions',prefix+'_rows'))
        records+=query(database,"""SELECT t.tgname AS name,t.tgenabled::text AS enabled,pg_get_triggerdef(t.oid) AS definition FROM pg_trigger t
            JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND c.relname=%s AND t.tgname=%s""",(spec.namespace,spec.table,prefix+'_trigger'))
        records+=query(database,"""SELECT p.proname AS name,pg_get_functiondef(p.oid) AS definition FROM pg_proc p
            JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.proname=%s""",(spec.namespace,prefix+'_capture'))
    else:
        records=[]
        for suffix in ('_meta','_versions','_rows'):
            name=prefix+suffix
            existing=query(database,'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',(spec.namespace,name))
            if existing:
                actual=query(database,'SHOW CREATE TABLE '+qualified(spec,name))[0]
                # AUTO_INCREMENT 是数据状态，不属于结构身份。
                import re
                records.append(dict(name=name,definition=re.sub(r' AUTO_INCREMENT=\d+','',actual['Create Table'])))
        records+=query(database,"""SELECT TRIGGER_NAME AS name,CONCAT(ACTION_TIMING,':',EVENT_MANIPULATION,':',EVENT_OBJECT_TABLE,':',ACTION_STATEMENT) AS definition
            FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s AND TRIGGER_NAME IN (%s,%s,%s)""",
            (spec.namespace,*(prefix+'_'+kind for kind in ('insert','update','delete'))))
    return {row['name']:hashlib.sha256(json.dumps(row,sort_keys=True,default=str).encode()).hexdigest() for row in records}


def validate_table(database,spec):
    """只接受普通表、唯一非空资源键和有限投影；拒绝引擎名称推断事务性。"""
    if spec.engine=='POSTGRESQL':
        rows=query(database,"""SELECT c.relkind::text AS kind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=%s AND c.relname=%s""",(spec.namespace,spec.table))
        keys=query(database,"""SELECT a.attname AS name,a.attnotnull AS required FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=i.indkey[0]
            WHERE n.nspname=%s AND c.relname=%s AND i.indisunique AND i.indisvalid AND i.indnkeyatts=1 AND i.indpred IS NULL AND i.indexprs IS NULL""",(spec.namespace,spec.table))
        valid=len(rows)==1 and rows[0]['kind']=='r' and any(row['name']==spec.resource_column and row['required'] for row in keys)
    else:
        rows=query(database,'SELECT TABLE_TYPE,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',(spec.namespace,spec.table))
        keys=query(database,"""SELECT min(COLUMN_NAME) AS name FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
            AND NON_UNIQUE=0 GROUP BY INDEX_NAME HAVING count(*)=1 AND max(SUB_PART) IS NULL""",(spec.namespace,spec.table))
        required=query(database,"""SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s AND IS_NULLABLE='NO'""",(spec.namespace,spec.table,spec.resource_column))
        valid=len(rows)==1 and rows[0]['TABLE_TYPE']=='BASE TABLE' and rows[0]['ENGINE']=='InnoDB' and required and any(row['name']==spec.resource_column for row in keys)
    if not valid:raise SourceReadError('DATABASE_TABLE_UNSUPPORTED')
    columns=','.join(quote(spec,name) for name in (spec.resource_column,spec.owner_column,*spec.fields))
    query(database,'SELECT '+columns+' FROM '+qualified(spec,spec.table)+' WHERE 1=0')


def preview_database_maintenance(var_dir,project_id,spec,purpose):
    # 移除必须绑定准确安装代次和已确认的对象；旧预览不能删除后来重新安装的组件。
    return maintenance_plan(spec,purpose,read_database_receipt(var_dir,project_id,spec))


def maintain_database(var_dir,project_id,spec,*,purpose,approved_fingerprint,operation_id,environ,cancelled=lambda:False):
    from product.backend.infrastructure.maintenance.inventory import exclusive_file
    path=installation_path(var_dir,project_id,spec)
    path.parent.mkdir(parents=True,exist_ok=True)
    with exclusive_file(path.with_suffix('.lock')):
        return _maintain_database(var_dir,project_id,spec,purpose=purpose,approved_fingerprint=approved_fingerprint,
            operation_id=operation_id,environ=environ,cancelled=cancelled)


def _maintain_database(var_dir,project_id,spec,*,purpose,approved_fingerprint,operation_id,environ,cancelled):
    plan=preview_database_maintenance(var_dir,project_id,spec,purpose)
    if purpose not in {'INSTALL_DATABASE','REMOVE_DATABASE'} or plan['fingerprint']!=approved_fingerprint or cancelled():
        raise SourceReadError('DATABASE_MAINTENANCE_AUTHORITY_REQUIRED')
    path=installation_path(var_dir,project_id,spec)
    path.parent.mkdir(parents=True,exist_ok=True)
    intent=path.with_name(path.stem+'.'+operation_id+'.intent')
    # 同一操作有写入痕迹后只读原回执，不靠重复 DDL 猜测第一次是否成功。
    try:
        with intent.open('x',encoding='ascii') as stream:
            stream.write(approved_fingerprint);stream.flush();os.fsync(stream.fileno())
    except FileExistsError:raise SourceReadError('DATABASE_MAINTENANCE_RECEIPT_UNKNOWN') from None
    previous=read_database_receipt(var_dir,project_id,spec)
    with connection(spec,environ) as database:
        validate_table(database,spec)
        actual=definitions(database,spec)
        if purpose=='INSTALL_DATABASE':
            if actual or previous is not None and previous.state!='REMOVED':raise SourceReadError('DATABASE_CAPTURE_OBJECT_CONFLICT')
            generation='sql_'+uuid4().hex
            partial=DatabaseInstallation(project_id=project_id,operation_id=operation_id,plan_fingerprint=approved_fingerprint,
                capture=spec,generation=generation,definitions={},state='INCOMPLETE',completed_at_us=time.time_ns()//1000)
            save_database_receipt(path,partial)
            for _name,sql in statements(spec):
                if cancelled():raise SourceReadError('DATABASE_MAINTENANCE_INTERRUPTED')
                query(database,sql)
                if spec.engine=='MYSQL':
                    # MySQL DDL 分别提交。仅登记已经回读的对象；未知的最后一条不能据意图补认。
                    partial=partial.model_copy(update={'definitions':definitions(database,spec),'completed_at_us':time.time_ns()//1000})
                    save_database_receipt(path,partial)
            query(database,'INSERT INTO '+qualified(spec,capture_key(spec)+'_meta')+' VALUES(%s,%s)',(generation,capture_key(spec)))
            database.commit()
            actual=definitions(database,spec)
            if set(actual)!={name for name,_ in statements(spec)}:raise SourceReadError('DATABASE_INSTALLATION_INCOMPLETE')
            receipt=DatabaseInstallation(project_id=project_id,operation_id=operation_id,plan_fingerprint=approved_fingerprint,
                capture=spec,generation=generation,definitions=actual,state='INSTALLED',completed_at_us=time.time_ns()//1000)
        else:
            if previous is None or actual!=previous.definitions:raise SourceReadError('DATABASE_CAPTURE_OWNERSHIP_CHANGED')
            remaining=dict(previous.definitions)
            for name,_sql in reversed(statements(spec)):
                if name not in remaining:continue
                if cancelled():raise SourceReadError('DATABASE_MAINTENANCE_INTERRUPTED')
                if spec.engine=='POSTGRESQL' and name.endswith('_trigger'):
                    sql='DROP TRIGGER '+quote(spec,name)+' ON '+qualified(spec,spec.table)
                else:
                    kind='FUNCTION' if name.endswith('_capture') else 'TRIGGER' if name.endswith(('_insert','_update','_delete')) else 'TABLE'
                    sql='DROP '+kind+' '+qualified(spec,name)+('()' if kind=='FUNCTION' else '')
                query(database,sql)
                remaining.pop(name)
                if spec.engine=='MYSQL':
                    save_database_receipt(path,previous.model_copy(update={'definitions':dict(remaining),'state':'REMOVING',
                        'operation_id':operation_id,'plan_fingerprint':approved_fingerprint,'completed_at_us':time.time_ns()//1000}))
            database.commit()
            receipt=previous.model_copy(update=dict(operation_id=operation_id,plan_fingerprint=approved_fingerprint,state='REMOVED',definitions={},completed_at_us=time.time_ns()//1000))
    save_database_receipt(path,receipt)
    return receipt


def read_database_source(var_dir,project_id,config,resource_id,*,scope=None,verified_subject=None,environ=None,cancelled=lambda:False):
    spec=config.database_capture
    installed=read_installation(var_dir,project_id,spec)
    if installed is None or cancelled():raise SourceReadError('DATABASE_CAPTURE_NOT_INSTALLED')
    with connection(spec,os.environ if environ is None else environ,readonly=True) as database:
        validate_table(database,spec)
        if definitions(database,spec)!=installed.definitions:raise SourceReadError('DATABASE_CAPTURE_OBJECTS_CHANGED')
        meta=query(database,'SELECT generation,config_hash FROM '+qualified(spec,capture_key(spec)+'_meta'))
        if len(meta)!=1 or (meta[0]['generation'],meta[0]['config_hash'])!=(installed.generation,capture_key(spec)):
            raise SourceReadError('DATABASE_CAPTURE_GENERATION_CHANGED')
        columns=','.join(quote(spec,name) for name in (spec.resource_column,spec.owner_column,*spec.fields))
        cast=lambda name:'CAST('+quote(spec,name)+(' AS text)' if spec.engine=='POSTGRESQL' else ' AS CHAR)')
        rows_table=qualified(spec,capture_key(spec)+'_rows')
        size=lambda name:'OCTET_LENGTH('+name+('::text)' if spec.engine=='POSTGRESQL' else ')')
        volume=query(database,'SELECT COALESCE(SUM(COALESCE('+size('before_data')+',0)+COALESCE('+size('after_data')+',0)+256),0) AS bytes FROM '+rows_table+' WHERE resource_id=%s',(resource_id,))[0]['bytes']
        projection=('jsonb_build_object' if spec.engine=='POSTGRESQL' else 'JSON_OBJECT')+'('+','.join("'"+name+"',"+quote(spec,name) for name in spec.fields)+')'
        sizes=query(database,'SELECT '+size(projection)+' AS bytes FROM '+qualified(spec,spec.table)+' WHERE '+cast(spec.resource_column)+'=%s LIMIT 2',(resource_id,))
        if volume>config.max_response_bytes or any(row['bytes']>config.max_response_bytes for row in sizes):
            raise SourceReadError('DATABASE_HISTORY_LIMIT')
        current=query(database,'SELECT '+columns+' FROM '+qualified(spec,spec.table)+' WHERE '+cast(spec.resource_column)+'=%s LIMIT 2',(resource_id,))
        if len(current)!=1:raise SourceReadError('DATABASE_RESOURCE_NOT_UNIQUE_OR_MISSING')
        history=query(database,'SELECT * FROM '+rows_table+' WHERE resource_id=%s ORDER BY row_version,seq LIMIT 4097',(resource_id,))
    if len(json.dumps(history,default=str).encode())>config.max_response_bytes:raise SourceReadError('DATABASE_HISTORY_LIMIT')
    groups=OrderedDict()
    for index,row in enumerate(history):
        if row['row_version']!=index+1:raise SourceReadError('DATABASE_HISTORY_DISCONTINUOUS')
        groups.setdefault(row['transaction_id'],[]).append(row)
    value=current[0]
    snapshot=RecordSnapshot(generation=installed.generation,collection=spec.table,resource_id=resource_id,
        owner_id=str(value[spec.owner_column]),version=len(groups),data={field:value[field] for field in spec.fields},
        last_operation_id='sql_'+next(reversed(groups)) if groups else None)
    operations=[]
    decode=lambda value:json.loads(value) if isinstance(value,(str,bytes)) else value
    for version,(transaction,rows) in enumerate(groups.items()):
        if scope is None or not any(row['request_nonce']==scope.request_nonce for row in rows):continue
        if verified_subject is None or any(row['request_nonce']!=scope.request_nonce or row['kind']!='UPDATE'
                or row['identity_changed'] or row['owner_id']!=snapshot.owner_id for row in rows):
            raise SourceReadError('DATABASE_COMMIT_CORRELATION_INVALID')
        if len(rows)>8 or len(operations)>=32:raise SourceReadError('DATABASE_HISTORY_LIMIT')
        operations.append(RecordOperation(operation_id='sql_'+transaction,generation=installed.generation,collection=spec.table,
            resource_id=resource_id,owner_id=snapshot.owner_id,subject_id=verified_subject,request_key=scope.request_nonce,
            scope_id=scope.scope_id,scope_ordinal=len(operations),before_version=version,after_version=version+1,
            transitions=tuple(RecordTransition(ordinal=index,before=decode(row['before_data']),after=decode(row['after_data'])) for index,row in enumerate(rows))))
    normalized=None if scope is None else scope.model_copy(update={'generation':installed.generation})
    if normalized is not None and any(row['request_nonce']=='late:'+scope.request_nonce for row in history):
        normalized=normalized.model_copy(update={'state':'INCOMPLETE'})
    return RecordProofView(snapshot=snapshot,scope=normalized,operations=tuple(operations))
