"""Linux/CI显式短期秘密提供者；正文只从继承的匿名管道进入当前服务内存。"""
from __future__ import annotations

import json
import os
import stat
import sys
import time
from threading import RLock

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.secrets.refs import validate_credential_secret_ref


class EphemeralSecretStore:
    """没有磁盘后备或枚举接口；期限不因读写延长，关闭与到期均丢弃内存引用。"""

    def __init__(self, values=None, *, lifetime_seconds=3600, clock=time.monotonic):
        if type(lifetime_seconds) is not int or not 60 <= lifetime_seconds <= 86400:
            raise ValueError('invalid session lifetime')
        self._clock, self._deadline = clock, clock()+lifetime_seconds
        self._values, self._lock, self._closed = {}, RLock(), False
        try:
            for reference,value in (values or {}).items():
                self.write(reference,value)
        except BaseException:
            self.close()
            raise

    def _active(self):
        if self._closed or self._clock() >= self._deadline:
            self._values.clear()
            self._closed = True
            return False
        return True

    def write(self, secret_ref, secret):
        validate_credential_secret_ref(secret_ref)
        if not isinstance(secret,str) or not secret or '\x00' in secret or len(secret.encode('utf-8'))>2560:
            raise ValueError('invalid private session secret')
        with self._lock:
            if not self._active():
                raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE,'短期秘密会话已结束，请重新配置启动会话')
            if secret_ref not in self._values and len(self._values)>=512:
                raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE,'短期秘密会话的引用数量已达上限')
            self._values[secret_ref]=secret

    def read(self, secret_ref):
        validate_credential_secret_ref(secret_ref)
        with self._lock:
            return self._values.get(secret_ref) if self._active() else None

    def configured(self, secret_ref):
        return bool(secret_ref and self.read(secret_ref))

    def delete(self, secret_ref):
        validate_credential_secret_ref(secret_ref)
        with self._lock:
            self._values.pop(secret_ref,None)

    def close(self):
        with self._lock:
            self._values.clear()
            self._closed=True

    def __repr__(self):
        return 'EphemeralSecretStore(<opaque>)'

    @classmethod
    def from_fd(cls, descriptor, *, lifetime_seconds=3600):
        """取得指定FD的所有权；只接受当前用户的匿名管道，最多5秒和1MiB，任何结果均关闭FD。"""
        if sys.platform!='linux' or type(descriptor) is not int or descriptor<3:
            raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE,'短期秘密注入需要Linux继承的匿名管道FD')
        import select
        raw=bytearray()
        try:
            info=os.fstat(descriptor)
            if not stat.S_ISFIFO(info.st_mode) or info.st_uid!=os.getuid() or not os.readlink('/proc/self/fd/'+str(descriptor)).startswith('pipe:['):
                raise ValueError('private injection requires anonymous pipe')
            deadline=time.monotonic()+5
            while True:
                remaining=deadline-time.monotonic()
                if remaining<=0 or not select.select([descriptor],[],[],remaining)[0]:
                    raise ValueError('private injection timed out')
                part=os.read(descriptor,65536)
                if not part:
                    break
                raw.extend(part)
                if len(raw)>1024*1024:
                    raise ValueError('private injection exceeds budget')
            value=json.loads(raw,object_pairs_hook=_distinct_fields)
            if not isinstance(value,dict) or set(value)!={'document_type','schema_version','values'} or value['document_type']!='jiejian.private-secret-session' or value['schema_version']!='1' or not isinstance(value['values'],dict):
                raise ValueError('private injection format')
            return cls(value['values'],lifetime_seconds=lifetime_seconds)
        except (OSError,ValueError,TypeError,RecursionError,JiejianError):
            # 私有输入及解析异常均不附带到公共错误或日志。
            raise JiejianError(ErrorCode.SECRET_STORE_UNAVAILABLE,'短期秘密注入未通过来源、格式或预算核对') from None
        finally:
            raw[:]=b'\x00'*len(raw)
            try:
                os.close(descriptor)
            except OSError:
                pass


def _distinct_fields(pairs):
    value={}
    for key,item in pairs:
        if key in value:
            raise ValueError('duplicate private input field')
        value[key]=item
    return value
