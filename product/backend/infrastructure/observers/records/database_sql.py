"""固定投影的方言 DDL；标识符只来自已验证声明，资源值一律绑定。"""
import hashlib
import json
from product.protocols.runtime.database_capture import DatabaseCapture


def capture_key(spec:DatabaseCapture):
    raw=json.dumps(spec.model_dump(mode='json'),sort_keys=True,separators=(',',':')).encode()
    return '_jj_'+hashlib.sha256(raw).hexdigest()[:20]


def quote(spec,name):
    mark='"' if spec.engine=='POSTGRESQL' else '`'
    return mark+name+mark


def qualified(spec,name):
    return quote(spec,spec.namespace)+'.'+quote(spec,name)


def statements(spec:DatabaseCapture):
    """审计行和版本行与业务写入同事务；单资源版本锁给出提交顺序。"""
    prefix=capture_key(spec)
    meta,versions,rows=(qualified(spec,prefix+suffix) for suffix in ('_meta','_versions','_rows'))
    table=qualified(spec,spec.table)
    key=lambda side:side+'.'+quote(spec,spec.resource_column)
    owner=lambda side:side+'.'+quote(spec,spec.owner_column)
    projection=lambda side:('jsonb_build_object' if spec.engine=='POSTGRESQL' else 'JSON_OBJECT')+'('+','.join(
        "'"+field+"',"+side+'.'+quote(spec,field) for field in spec.fields)+')'
    if spec.engine=='POSTGRESQL':
        function=qualified(spec,prefix+'_capture')
        result=[(prefix+'_meta',f'CREATE TABLE {meta}(generation text NOT NULL,config_hash text NOT NULL)'),
            (prefix+'_versions',f'CREATE TABLE {versions}(resource_id text PRIMARY KEY,version bigint NOT NULL)'),
            (prefix+'_rows',f'''CREATE TABLE {rows}(seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                resource_id text NOT NULL,owner_id text NOT NULL,kind text NOT NULL,request_nonce text,
                transaction_id text NOT NULL,row_version bigint NOT NULL,before_data jsonb,after_data jsonb,
                identity_changed integer NOT NULL,UNIQUE(resource_id,row_version))'''),
            (prefix+'_capture',f'''CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $jj$
                DECLARE rid text; oid text; previous jsonb; subsequent jsonb; v bigint; invalid integer:=0;
                BEGIN
                  IF TG_OP='DELETE' THEN rid:={key('OLD')}::text;oid:={owner('OLD')}::text;
                  ELSE rid:={key('NEW')}::text;oid:={owner('NEW')}::text; END IF;
                  IF TG_OP<>'INSERT' THEN previous:={projection('OLD')};END IF;
                  IF TG_OP<>'DELETE' THEN subsequent:={projection('NEW')};END IF;
                  IF TG_OP='UPDATE' AND ({key('OLD')} IS DISTINCT FROM {key('NEW')} OR {owner('OLD')} IS DISTINCT FROM {owner('NEW')}) THEN invalid:=1;END IF;
                  INSERT INTO {versions} AS counter VALUES(rid,1) ON CONFLICT(resource_id) DO UPDATE SET version=counter.version+1 RETURNING version INTO v;
                  INSERT INTO {rows}(resource_id,owner_id,kind,request_nonce,transaction_id,row_version,before_data,after_data,identity_changed)
                    VALUES(rid,oid,TG_OP,NULLIF(current_setting('jiejian.nonce',true),''),pg_current_xact_id()::text,v,previous,subsequent,invalid);
                  RETURN NULL;
                END $jj$''')]
        result.append((prefix+'_trigger',f'CREATE TRIGGER {quote(spec,prefix+"_trigger")} AFTER INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION {function}()'))
        return tuple(result)
    result=[(prefix+'_meta',f'CREATE TABLE {meta}(generation varchar(64) NOT NULL,config_hash char(64) NOT NULL) ENGINE=InnoDB'),
        (prefix+'_versions',f'CREATE TABLE {versions}(resource_id varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin PRIMARY KEY,version bigint NOT NULL) ENGINE=InnoDB'),
        (prefix+'_rows',f'''CREATE TABLE {rows}(seq bigint AUTO_INCREMENT PRIMARY KEY,
            resource_id varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,owner_id varchar(128) NOT NULL,
            kind varchar(8) NOT NULL,request_nonce varchar(80),transaction_id varchar(64) NOT NULL,
            row_version bigint NOT NULL,before_data JSON,after_data JSON,identity_changed integer NOT NULL,
            UNIQUE KEY resource_history(resource_id,row_version)) ENGINE=InnoDB''')]
    for kind in ('INSERT','UPDATE','DELETE'):
        side='OLD' if kind=='DELETE' else 'NEW'
        before='NULL' if kind=='INSERT' else projection('OLD')
        after='NULL' if kind=='DELETE' else projection('NEW')
        invalid=f'NOT({key("OLD")} <=> {key("NEW")}) OR NOT({owner("OLD")} <=> {owner("NEW")})' if kind=='UPDATE' else '0'
        name=prefix+'_'+kind.lower()
        result.append((name,f'''CREATE TRIGGER {qualified(spec,name)} AFTER {kind} ON {table} FOR EACH ROW
            BEGIN
              DECLARE v bigint;
              INSERT INTO {versions} VALUES(CAST({key(side)} AS CHAR),1) ON DUPLICATE KEY UPDATE version=version+1;
              SELECT version INTO v FROM {versions} WHERE resource_id=CAST({key(side)} AS CHAR);
              INSERT INTO {rows}(resource_id,owner_id,kind,request_nonce,transaction_id,row_version,before_data,after_data,identity_changed)
                VALUES(CAST({key(side)} AS CHAR),CAST({owner(side)} AS CHAR),'{kind}',@jiejian_nonce,
                    COALESCE(@jiejian_transaction,CONCAT('unknown_',CONNECTION_ID())),v,{before},{after},{invalid});
            END'''))
    return tuple(result)


def maintenance_plan(spec,purpose,installation=None):
    objects=tuple(name for name,_sql in statements(spec))
    if purpose=='REMOVE_DATABASE':objects=tuple(name for name in objects if installation is not None and name in installation.definitions)
    material=dict(purpose=purpose,config=spec.model_dump(mode='json'),objects=objects,
        ddl_sha256=hashlib.sha256('\n'.join(sql for _,sql in statements(spec)).encode()).hexdigest())
    if purpose=='REMOVE_DATABASE':
        material['installation']=None if installation is None else installation.model_dump(mode='json')
    fingerprint=hashlib.sha256(json.dumps(material,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(**material,fingerprint=fingerprint,transactional_ddl=spec.engine=='POSTGRESQL')
