# 显式会话秘密的内存覆盖层；普通凭据委托原 SecretStore，会话引用永不写入平台存储。
from threading import RLock


class SessionSecretOverlay:
    """仅 set_session 登记的精确引用使用内存；清除后保留无秘密墓碑，避免误删平台凭据。"""
    def __init__(self, persistent):
        self._persistent = persistent
        self._values = {}
        self._owners = {}
        self._lock = RLock()

    def set_session(self, session_id, reference, value):
        with self._lock:
            if not reference.startswith("cred:jiejian/test-identity/") or not value or len(self._owners)>=4096 and reference not in self._owners:
                raise ValueError("session secret boundary")
            owner = self._owners.get(reference)
            if owner is not None and owner != session_id:
                raise ValueError("session secret owner mismatch")
            self._owners[reference] = session_id
            self._values[reference] = value

    def clear_session(self, session_id):
        with self._lock:
            for reference,owner in self._owners.items():
                if owner==session_id:
                    self._values.pop(reference,None)

    def clear(self):
        with self._lock:
            self._values.clear()

    def read(self, reference):
        with self._lock:
            if reference in self._owners:
                return self._values.get(reference)
        return self._persistent.read(reference)

    def configured(self, reference):
        with self._lock:
            if reference in self._owners:
                return bool(self._values.get(reference))
        return self._persistent.configured(reference)

    def write(self, reference, value):
        with self._lock:
            if reference in self._owners:
                self._values[reference] = value
                return
        self._persistent.write(reference,value)

    def delete(self, reference):
        with self._lock:
            if reference in self._owners:
                self._values.pop(reference,None)
                return
        self._persistent.delete(reference)

    def __repr__(self):
        return "SessionSecretOverlay(<opaque>)"
