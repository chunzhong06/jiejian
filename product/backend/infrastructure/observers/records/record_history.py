# 校验独占记录日志的完整哈希链，拒绝不支持的格式和截断记录。
from __future__ import annotations
import hashlib
import os
import struct



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


