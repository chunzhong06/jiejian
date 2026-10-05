# Observer 调用与结果文件共用的原子替换；路径授权和失败分类仍由各观察器负责。
import os
from pathlib import Path


def write_atomic(path: Path, payload: bytes) -> None:
    """替换既有父目录下的文件；失败保留 OSError，并回收本次临时文件。"""
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
