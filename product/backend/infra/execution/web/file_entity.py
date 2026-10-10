# 在网络边界内解释文件实体；正式检查只返回摘要，私有原文仅交显式取样端口。
from dataclasses import dataclass
import hashlib
import re
from typing import Callable


@dataclass(frozen=True)
class FileEntityPolicy:
    max_bytes:int
    private_capture:Callable[[bytes],None]|None=None

    def __post_init__(self):
        if type(self.max_bytes) is not int or not 1<=self.max_bytes<=4*1024*1024:
            raise ValueError('invalid file response budget')


@dataclass(frozen=True)
class FileEntityReceipt:
    actual_size:int
    actual_sha256:str|None
    complete:bool
    refused:bool
    reason_codes:tuple[str,...]=()


def receive_file_entity(response,policy,*,max_bytes,known_secrets,cancelled):
    """只用完整解码实体计算摘要；目标声明的长度或摘要从不参与内容判断。"""
    import httpx
    limit=min(policy.max_bytes,max_bytes)
    content=bytearray()
    reason=None
    try:
        for chunk in response.iter_bytes():
            if cancelled():
                reason='FILE_RECEIVE_CANCELLED';break
            if len(content)+len(chunk)>limit:
                reason='FILE_RESPONSE_TOO_LARGE';break
            content.extend(chunk)
    except httpx.RequestError:
        reason='FILE_RESPONSE_INTERRUPTED'
    if reason is not None:
        return FileEntityReceipt(len(content),None,False,False,(reason,))
    raw=bytes(content)
    # 取样不能持久化回显秘密；正式检查同样不把含秘密内容转成可采用证据。
    secret=any(value and value.encode() in raw for value in known_secrets) or bool(re.search(
        rb'(?i)(?:\bBearer\s+\S+|\b(?:password|token|api[_-]?key)\s*[:=]\s*\S+)',raw))
    if secret:return FileEntityReceipt(len(raw),None,False,False,('FILE_RESPONSE_SENSITIVE',))
    if not raw:return FileEntityReceipt(0,None,False,False,('FILE_RESPONSE_EMPTY',))
    if response.status_code==206 or 300<=response.status_code<400:
        return FileEntityReceipt(len(raw),None,False,False,('FILE_RESPONSE_PARTIAL_OR_REDIRECT',))
    refused=False
    if response.status_code in {401,403} and len(raw)<=8192:
        try:
            from product.backend.infra.observers.adapters.json_source import strict_json
            data=strict_json(raw,8192)
            refused=isinstance(data,dict) and set(data)<={'error'} and all(isinstance(item,str) and len(item)<=512 for item in data.values())
        except ValueError:pass
    receipt=FileEntityReceipt(len(raw),hashlib.sha256(raw).hexdigest(),True,refused)
    if policy.private_capture is not None and 200<=response.status_code<300:
        policy.private_capture(raw)
    return receipt
