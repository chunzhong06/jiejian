# 校验独占记录日志并迁移最终业务状态；旧操作与旧文件保留，新代际不继承旧观察窗口。
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import struct

from product.backend.infra.runtime.process.exclusive_file import open_exclusive_record_file
from product.protocols.runtime.transaction_records import RecordSeed, RecordStateMigration


def read_history(stream, version):
    """验证完整哈希链后返回最终内存库；空文件由调用方决定是否允许初始化。"""
    magic=f'JIEJIAN-TRANSACTION-RECORDS-{version}\n'.encode('ascii')
    size=os.fstat(stream.fileno()).st_size
    stream.seek(0)
    if size==0:return None,bytes(32)
    if size>128*1024*1024 or stream.read(len(magic))!=magic:
        raise ValueError('RECORD_HISTORY_INVALID')
    digest,latest=bytes(32),None
    while stream.tell()<size:
        length_raw=stream.read(4)
        if len(length_raw)!=4:raise ValueError('RECORD_HISTORY_INCOMPLETE')
        length=struct.unpack('>I',length_raw)[0]
        if not 1<=length<=128*1024*1024:raise ValueError('RECORD_HISTORY_INVALID')
        data=stream.read(length);next_digest=stream.read(32)
        if len(data)!=length or len(next_digest)!=32 or hashlib.sha256(digest+length_raw+data).digest()!=next_digest:
            raise ValueError('RECORD_HISTORY_INCOMPLETE')
        digest,latest=next_digest,data
    if latest is None:raise ValueError('RECORD_HISTORY_INCOMPLETE')
    return latest,digest


def import_legacy_state(path, target, generation, persist):
    """旧日志独占只读至新状态持久完成；新库仅种入资源与所有者，所有版本从零开始。"""
    with open_exclusive_record_file(path,read_only=True) as stream:
        raw,history_hash=read_history(stream,1)
        if raw is None:raise ValueError('RECORD_HISTORY_INCOMPLETE')
        source=sqlite3.connect(':memory:')
        try:
            source.deserialize(raw)
            source.execute('PRAGMA trusted_schema=OFF');source.execute('PRAGMA query_only=ON')
            if source.execute('PRAGMA integrity_check').fetchone()!=('ok',):raise ValueError('RECORD_HISTORY_INVALID')
            metadata=source.execute('SELECT format,generation FROM metadata WHERE singleton=1').fetchone()
            if metadata is None or metadata[0]!=1:raise ValueError('RECORD_STORE_FORMAT_UNSUPPORTED')
            seeds=[]
            for collection,resource,owner,data in source.execute('SELECT collection,resource_id,owner_id,data FROM resources ORDER BY collection,resource_id'):
                seeds.append(RecordSeed.model_validate_json(json.dumps({'collection':collection,'resource_id':resource,'owner_id':owner,'data':json.loads(data)},allow_nan=False)))
            def state_hash(items):
                return hashlib.sha256(json.dumps([item.model_dump(mode='json') for item in items],ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            target.execute('BEGIN IMMEDIATE')
            try:
                target.executemany('INSERT INTO resources VALUES(?,?,?,?,?,NULL)',
                    [(seed.collection,seed.resource_id,seed.owner_id,0,json.dumps(seed.data,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)) for seed in seeds])
                restored=[RecordSeed.model_validate_json(json.dumps({'collection':c,'resource_id':r,'owner_id':o,'data':json.loads(d)},allow_nan=False))
                    for c,r,o,d in target.execute('SELECT collection,resource_id,owner_id,data FROM resources ORDER BY collection,resource_id')]
                receipt=RecordStateMigration(source_generation=metadata[1],target_generation=generation,
                    source_history_sha256=history_hash.hex(),source_state_sha256=state_hash(seeds),target_state_sha256=state_hash(restored),resource_count=len(seeds))
                target.execute('UPDATE metadata SET migration=? WHERE singleton=1',(receipt.model_dump_json(),))
                target.execute('COMMIT')
                persist()
            except BaseException:
                if target.in_transaction:target.execute('ROLLBACK')
                raise
        except sqlite3.Error:
            raise ValueError('RECORD_HISTORY_INVALID') from None
        finally:source.close()
