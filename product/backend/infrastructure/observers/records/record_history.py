# 校验独占记录日志的完整哈希链，拒绝不支持的格式和截断记录。
from __future__ import annotations
import hashlib
import os
import struct
import zlib

HISTORY_LIMIT = 128 * 1024 * 1024
_CHECKPOINT = b'JJC1'
_DELTA = b'JJD1'


def _page_size(image):
    size = struct.unpack('>H', image[16:18])[0]
    return 65536 if size == 1 else size


def encode_frame(image, previous, *, checkpoint=False):
    """生成独占日志载荷；检查点保留整库业务历史，增量只改变物理保存方式。"""
    if len(image) > HISTORY_LIMIT:
        raise ValueError('RECORD_HISTORY_LIMIT')
    page_size = _page_size(image)
    if previous is None or checkpoint or _page_size(previous) != page_size:
        return _CHECKPOINT + struct.pack('>I', len(image)) + zlib.compress(image)
    changed = [offset for offset in range(0, len(image), page_size)
               if image[offset:offset + page_size] != previous[offset:offset + page_size]]
    if len(changed) * page_size > len(image) // 2:
        return _CHECKPOINT + struct.pack('>I', len(image)) + zlib.compress(image)
    delta = struct.pack('>III', len(image), page_size, len(changed)) + b''.join(
        struct.pack('>I', offset // page_size) + image[offset:offset + page_size] for offset in changed)
    return _DELTA + zlib.compress(delta)


def _inflate(raw, maximum):
    stream = zlib.decompressobj()
    value = stream.decompress(raw, maximum + 1)
    if len(value) > maximum or not stream.eof or stream.unused_data or stream.unconsumed_tail:
        raise ValueError('RECORD_HISTORY_INVALID')
    return value


def _apply_frame(data, image):
    if data.startswith(b'SQLite format 3\x00'):
        return bytearray(data)
    if data.startswith(_CHECKPOINT) and len(data) > 8:
        size = struct.unpack('>I', data[4:8])[0]
        if not 0 < size <= HISTORY_LIMIT:
            raise ValueError('RECORD_HISTORY_INVALID')
        value = _inflate(data[8:], size)
        if len(value) != size:
            raise ValueError('RECORD_HISTORY_INCOMPLETE')
        return bytearray(value)
    if not data.startswith(_DELTA) or image is None:
        raise ValueError('RECORD_HISTORY_INVALID')
    delta = _inflate(data[4:], HISTORY_LIMIT + HISTORY_LIMIT // 512 * 4 + 12)
    if len(delta) < 12:
        raise ValueError('RECORD_HISTORY_INCOMPLETE')
    size, page_size, count = struct.unpack('>III', delta[:12])
    if (not 0 < size <= HISTORY_LIMIT or page_size != _page_size(image)
            or not 512 <= page_size <= 65536 or page_size & (page_size - 1)
            or size % page_size or count > size // page_size
            or len(delta) != 12 + count * (4 + page_size)):
        raise ValueError('RECORD_HISTORY_INVALID')
    if len(image) < size:
        image.extend(bytes(size - len(image)))
    else:
        del image[size:]
    previous = -1
    for cursor in range(12, len(delta), 4 + page_size):
        page = struct.unpack('>I', delta[cursor:cursor + 4])[0]
        if page <= previous or page >= size // page_size:
            raise ValueError('RECORD_HISTORY_INVALID')
        offset = page * page_size
        image[offset:offset + page_size] = delta[cursor + 4:cursor + 4 + page_size]
        previous = page
    return image



def read_history(stream, version):
    """验证完整哈希链后返回最终内存库；空文件由调用方决定是否允许初始化。"""
    magic=f'JIEJIAN-TRANSACTION-RECORDS-{version}\n'.encode('ascii')
    size=os.fstat(stream.fileno()).st_size
    stream.seek(0)
    if size==0:return None,bytes(32)
    if size>HISTORY_LIMIT or stream.read(len(magic))!=magic:
        raise ValueError('RECORD_HISTORY_INVALID')
    digest,latest=bytes(32),None
    while stream.tell()<size:
        length_raw=stream.read(4)
        if len(length_raw)!=4:raise ValueError('RECORD_HISTORY_INCOMPLETE')
        length=struct.unpack('>I',length_raw)[0]
        if not 1<=length<=HISTORY_LIMIT:raise ValueError('RECORD_HISTORY_INVALID')
        data=stream.read(length);next_digest=stream.read(32)
        if len(data)!=length or len(next_digest)!=32 or hashlib.sha256(digest+length_raw+data).digest()!=next_digest:
            raise ValueError('RECORD_HISTORY_INCOMPLETE')
        try:latest = _apply_frame(data, latest)
        except (zlib.error, struct.error):raise ValueError('RECORD_HISTORY_INVALID') from None
        digest=next_digest
    if latest is None:raise ValueError('RECORD_HISTORY_INCOMPLETE')
    return bytes(latest),digest


