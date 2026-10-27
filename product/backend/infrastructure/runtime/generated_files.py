# 由实际写入者登记日志与缓存的归属；清理器不根据所在目录推断文件属于界鉴。
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

_ROOTS = {
    'assistant-cache':'cache/assistant', 'app-log':'logs/app', 'worker-log':'logs/workers',
    'identity-log':'logs/identity-preparations', 'sample-log':'logs/official-samples', 'startup-log':'logs/startup',
}


def _reference(var_dir: Path, path: Path, producer: str) -> tuple[Path,str]:
    root = var_dir.resolve()
    if producer not in _ROOTS or not path.resolve().is_relative_to(root / _ROOTS[producer]):
        raise ValueError('生成文件登记越界')
    relative = path.resolve().relative_to(root).as_posix()
    receipt = root / 'runtime/generated-files' / (hashlib.sha256(relative.encode()).hexdigest()+'.json')
    return receipt, relative


def register_generated_file(var_dir: Path, path: Path, producer: str) -> bool:
    """生产者写入成功后登记，不收录文件正文或凭据。"""
    receipt, relative = _reference(var_dir,path,producer)
    try:
        receipt.parent.mkdir(parents=True,exist_ok=True)
        temporary = receipt.with_suffix(f'.{uuid4().hex}.tmp')
        temporary.write_text(json.dumps({'schema_version':'1','kind':'generated-file','producer':producer,'path':relative}),encoding='utf-8')
        os.replace(temporary,receipt)
        return True
    except OSError:
        # 登记失败只使文件保持未知，不能让日志或缓存故障改变业务执行结果。
        return False


def generated_file_owner(var_dir: Path, path: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(var_dir.resolve()).as_posix()
        receipt = var_dir / 'runtime/generated-files' / (hashlib.sha256(relative.encode()).hexdigest()+'.json')
        if receipt.is_symlink() or receipt.stat().st_size > 8192:
            return None
        value=json.loads(receipt.read_text(encoding='utf-8-sig'))
        producer=value.get('producer')
        if value.get('schema_version')!='1' or value.get('kind')!='generated-file' or value.get('path')!=relative:
            return None
        _reference(var_dir,path,producer)
        return producer
    except (OSError,ValueError,TypeError,AttributeError):
        return None


def forget_generated_file(var_dir: Path, path: Path, producer: str) -> None:
    """生产者移走临时文件或清理成功后回收对应登记，不留下无限增长的孤立索引。"""
    receipt, _ = _reference(var_dir,path,producer)
    try:
        receipt.unlink(missing_ok=True)
    except OSError:
        pass
