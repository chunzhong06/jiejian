# 记录来源读取能力的短期受控存储；DPAPI 加密值仅留运行边界，不进入协议、日志或证据。
from pathlib import Path
import re

from pydantic import TypeAdapter
from product.protocols.runtime_identity import InstanceId


def _path(var_dir: Path, instance_id: str) -> Path:
    TypeAdapter(InstanceId).validate_python(instance_id, strict=True)
    value = var_dir.resolve() / 'runtime' / 'record-capabilities' / (instance_id + '.bin')
    if value.resolve() != value.absolute() or value.is_symlink():
        raise ValueError('record capability path invalid')
    return value


def save_record_capability(var_dir: Path, instance_id: str, value: str):
    import win32crypt
    if re.fullmatch(r'[A-Za-z0-9_-]{43}', value) is None:
        raise ValueError('record capability invalid')
    path = _path(var_dir, instance_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    protected = win32crypt.CryptProtectData(value.encode('ascii'), 'Jiejian runtime record access',
        b'jiejian-record-read-v1', None, None, 1)
    with path.open('xb') as stream:
        stream.write(protected)


def read_record_capability(var_dir: Path, instance_id: str) -> str:
    import win32crypt
    path = _path(var_dir, instance_id)
    try:
        if path.stat().st_size > 4096:
            raise ValueError()
        value = win32crypt.CryptUnprotectData(path.read_bytes(), b'jiejian-record-read-v1', None, None, 1)[1].decode('ascii')
        if re.fullmatch(r'[A-Za-z0-9_-]{43}', value) is None:
            raise ValueError()
        return value
    except Exception:
        raise ValueError('record read capability unavailable') from None


def discard_record_capability(var_dir: Path, instance_id: str):
    _path(var_dir, instance_id).unlink(missing_ok=True)
