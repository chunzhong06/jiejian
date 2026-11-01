from __future__ import annotations

from collections import OrderedDict
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from product.backend.domain.boundaries.entities import boundary_sha256

from product.backend.infrastructure.observers.adapters.json_source import SourceReadError
from product.backend.infrastructure.runtime.process.controlled.node_owned import node_artifact_store
from product.protocols.runtime.node_runtime import NodeRuntimeManifest
from product.protocols.runtime.transaction_records import RecordSnapshot, RecordOperation, RecordTransition, RecordProofView


def sqlite_selection(var_dir, reference, config):
    manifest = NodeRuntimeManifest.model_validate_json((node_artifact_store(var_dir) / reference.instance_id / 'launch.json').read_bytes())
    for index, database in enumerate(manifest.sqlite):
        if database.relative_path != config.database_path:
            continue
        for table in database.tables:
            if (table.table, table.resource_column, table.owner_column) == (config.table, config.resource_column, config.owner_column) and config.protected_column in table.fields and set(table.fields)==set(config.observed_columns or (config.protected_column,)):
                return index, database, table
    raise SourceReadError('SQLITE_CAPTURE_MAPPING_MISSING')


def read_sqlite_source(var_dir, reference, config, resource_id, *, scope=None, verified_subject=None, cancelled=lambda: False):
    """将同事务审计归约成提交单元；同一事务内部改回原值不冒充独立提交。"""
    index, specification, table = sqlite_selection(var_dir, reference, config)
    path = Path(var_dir).resolve() / 'data/controlled-applications' / reference.project_id / 'sqlite' / f'{index}.sqlite'
    if cancelled() or path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise SourceReadError('SQLITE_CAPTURE_UNAVAILABLE')
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)) as database:
            database.row_factory = sqlite3.Row
            database.execute('BEGIN')
            metadata = database.execute('SELECT generation,config FROM _jj_meta').fetchone()
            if metadata is None or json.loads(metadata['config']) != specification.model_dump(mode='json'):
                raise SourceReadError('SQLITE_CAPTURE_CONFIGURATION_CHANGED')
            expected = {'_jj_' + str(index) + '_' + table.table + '_' + operation for operation in ('insert', 'update', 'delete')}
            triggers = database.execute('SELECT name,sql FROM sqlite_schema WHERE type=? AND tbl_name=?', ('trigger', table.table)).fetchall()
            if not expected.issubset({row['name'] for row in triggers}) or any('_jj_rows' not in row['sql'] or '_jj_nonce' not in row['sql'] for row in triggers if row['name'] in expected):
                raise SourceReadError('SQLITE_CAPTURE_TRIGGERS_CHANGED')
            journal_bytes=database.execute('SELECT COALESCE(SUM(COALESCE(length(CAST(before_data AS BLOB)),0)+COALESCE(length(CAST(after_data AS BLOB)),0)+256),0) FROM _jj_rows WHERE table_name=?',(table.table,)).fetchone()[0]
            if journal_bytes>config.max_response_bytes:raise SourceReadError('SQLITE_CAPTURE_LIMIT')
            selected_columns=(table.resource_column,table.owner_column,*table.fields)
            unsupported=' OR '.join('typeof("'+name+'")=\'blob\'' for name in selected_columns)
            if database.execute('SELECT 1 FROM "'+table.table+'" WHERE '+unsupported+' LIMIT 1').fetchone():
                raise SourceReadError('SQLITE_CAPTURE_VALUE_UNSUPPORTED')
            if database.execute('SELECT 1 FROM _jj_rows WHERE table_name=? AND identity_changed=2 LIMIT 1',(table.table,)).fetchone():
                raise SourceReadError('SQLITE_CAPTURE_VALUE_UNSUPPORTED')
            if config.source_kind=='SQLITE_OBJECTS':
                return _creation_view(database,metadata['generation'],table,scope)
            columns = ','.join('"' + column + '"' for column in (table.resource_column, table.owner_column, *table.fields))
            rows = database.execute(f'SELECT {columns} FROM "{table.table}" WHERE CAST("{table.resource_column}" AS TEXT)=? LIMIT 2', (resource_id,)).fetchall()
            if len(rows) != 1:
                raise SourceReadError('SQLITE_RESOURCE_MISSING' if not rows else 'SQLITE_RESOURCE_KEY_NOT_UNIQUE')
            current = rows[0]
            if scope is not None and database.execute('SELECT 1 FROM _jj_rows WHERE request_nonce=? AND identity_changed<>0 LIMIT 1',(scope.request_nonce,)).fetchone():
                raise SourceReadError('SQLITE_RESOURCE_IDENTITY_CHANGED')
            history = database.execute('SELECT * FROM _jj_rows WHERE table_name=? AND resource_id=? ORDER BY seq LIMIT 4097', (table.table, resource_id)).fetchall()
            if len(history) > 4096:
                raise SourceReadError('SQLITE_CAPTURE_LIMIT')
            groups = OrderedDict()
            for row in history:
                groups.setdefault(row['transaction_id'], []).append(row)
            generation = metadata['generation']
            snapshot = RecordSnapshot(generation=generation, collection=table.table, resource_id=resource_id,
                owner_id=str(current[table.owner_column]), version=len(groups),
                data={field: current[field] for field in table.fields},
                last_operation_id='sql_' + next(reversed(groups)) if groups else None)
            operations = []
            normalized_scope = scope.model_copy(update={'generation': generation}) if scope is not None else None
            for version, (transaction, changes) in enumerate(groups.items()):
                if scope is None or not any(row['request_nonce'] == scope.request_nonce for row in changes):
                    continue
                if verified_subject is None or any(row['request_nonce'] != scope.request_nonce or row['kind'] != 'UPDATE' or row['owner_id'] != snapshot.owner_id for row in changes):
                    raise SourceReadError('SQLITE_COMMIT_CORRELATION_INVALID')
                if len(changes) > 8 or len(operations) >= 32:
                    raise SourceReadError('SQLITE_CAPTURE_LIMIT')
                transitions = tuple(RecordTransition(ordinal=ordinal, before=json.loads(row['before_data']), after=json.loads(row['after_data'])) for ordinal, row in enumerate(changes))
                operations.append(RecordOperation(operation_id='sql_' + transaction, generation=generation,
                    collection=table.table, resource_id=resource_id, owner_id=snapshot.owner_id,
                    subject_id=verified_subject, request_key=scope.request_nonce, scope_id=scope.scope_id,
                    scope_ordinal=len(operations), before_version=version, after_version=version + 1, transitions=transitions))
            if scope is not None and database.execute('SELECT 1 FROM _jj_rows WHERE request_nonce=? LIMIT 1', ('late:' + scope.request_nonce,)).fetchone():
                normalized_scope = normalized_scope.model_copy(update={'state': 'INCOMPLETE'})
            return RecordProofView(snapshot=snapshot, scope=normalized_scope, operations=tuple(operations))
    except sqlite3.Error:
        raise SourceReadError('SQLITE_CAPTURE_READ_FAILED') from None
    except SourceReadError:
        raise
    except (ValueError,TypeError):
        raise SourceReadError('SQLITE_CAPTURE_VALUE_UNSUPPORTED') from None


def _creation_view(database,generation,table,scope):
    from product.protocols.runtime.creation_records import CreationView,CreationMember,CreationEvent
    rows=database.execute('SELECT * FROM _jj_rows WHERE table_name=? ORDER BY seq LIMIT 4097',(table.table,)).fetchall()
    columns=','.join('"'+name+'"' for name in (table.resource_column,table.owner_column,*table.fields))
    current=database.execute('SELECT '+columns+' FROM "'+table.table+'" ORDER BY "'+table.resource_column+'" LIMIT 257').fetchall()
    if len(rows)>4096 or len(current)>256:raise SourceReadError('SQLITE_CREATION_LIMIT')
    normalized=scope.model_copy(update={'generation':generation}) if scope else None
    groups=OrderedDict()
    for row in rows:
        groups.setdefault((row['transaction_id'],row['resource_id']),[]).append(row)
    incarnations={}
    versions={}
    events=[]
    foreign=False
    for (_transaction,key),changes in groups.items():
        before,after=json.loads(changes[0]['before_data']) if changes[0]['before_data'] else None,json.loads(changes[-1]['after_data']) if changes[-1]['after_data'] else None
        first,last=changes[0],changes[-1]
        if before is None and after is None:
            # 同一事务内新建再删除未发布对象；混杂请求或身份变化仍不能解释为完整缺席。
            if scope and any(row['request_nonce']==scope.request_nonce for row in changes):
                foreign |= any(row['request_nonce']!=scope.request_nonce or row['identity_changed'] for row in changes)
            continue
        incarnation=incarnations.get(key,'seed_'+boundary_sha256(dict(table=table.table,key=key))[:32])
        if before is None and after is not None:
            versions[key]=0
            incarnation='created_'+str(first['seq'])
            incarnations[key]=incarnation
            kind='CREATE'
        elif before is not None and after is None:
            kind='REMOVE'
        else:
            versions[key]=versions.get(key,0)+1
            if scope and any(row['request_nonce']==scope.request_nonce for row in changes):foreign=True
            continue
        member=CreationMember(resource_id=key,owner_id=last['owner_id'],incarnation=incarnation,version=versions.get(key,0),data_digest=boundary_sha256(after if after is not None else before))
        if scope and any(row['request_nonce']==scope.request_nonce for row in changes):
            if any(row['request_nonce']!=scope.request_nonce or row['identity_changed'] for row in changes):foreign=True
            events.append(CreationEvent(sequence=last['seq'],scope_id=scope.scope_id,kind=kind,member=member))
    if len(events)>32:raise SourceReadError('SQLITE_CREATION_LIMIT')
    members=tuple(sorted((CreationMember(resource_id=str(row[table.resource_column]),owner_id=str(row[table.owner_column]),
        incarnation=incarnations.get(str(row[table.resource_column]),'seed_'+boundary_sha256(dict(table=table.table,key=str(row[table.resource_column])))[:32]),
        version=versions.get(str(row[table.resource_column]),0),data_digest=boundary_sha256({name:row[name] for name in table.fields})) for row in current),key=lambda item:item.resource_id))
    if scope and any(row['request_nonce']=='late:'+scope.request_nonce for row in rows):normalized=normalized.model_copy(update={'state':'INCOMPLETE'})
    return CreationView(schema_version='1',generation=generation,collection=table.table,watermark=rows[-1]['seq'] if rows else 0,
        members=members,scope=normalized,events=tuple(sorted(events,key=lambda item:item.sequence)),foreign_mutations=foreign)
