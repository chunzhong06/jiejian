# 验证官方示例清单与源码复制边界。
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from product.backend.domain.errors import ErrorCode, JiejianError
from .models import OfficialSampleInstallation


_MANIFEST_FIELDS = {
    "schema_version",
    "sample_id",
    "display_name",
    "source_root",
    "entry_module",
    "health_path",
}


_EXPECTED_MANIFEST = {
    "schema_version": "1",
    "sample_id": "collaboration-space",
    "display_name": "协作空间",
    "source_root": "source",
    "entry_module": "server",
    "health_path": "/health",
}


_MAX_MANIFEST_BYTES = 16_384


def _load_installation(root: Path | None) -> OfficialSampleInstallation:
    if root is None:
        return OfficialSampleInstallation(
            available=False,
            reason="未配置官方示例目录",
        )
    try:
        resolved = root.expanduser().resolve(strict=True)
        if not resolved.is_dir() or resolved.is_symlink():
            raise ValueError("sample root")
        manifest_path = resolved / "sample.json"
        raw = manifest_path.read_bytes()
        if not raw or len(raw) > _MAX_MANIFEST_BYTES:
            raise ValueError("manifest size")
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(manifest, dict):
            raise ValueError("manifest object")
        node = manifest.get('schema_version') == '2'
        if node:
            if set(manifest) != {'schema_version','sample_id','display_name','source_root','runtime_kind','entry','files','health_path'}:
                raise ValueError('manifest fields')
            if (manifest['sample_id'],manifest['display_name'],manifest['source_root'],manifest['runtime_kind'],manifest['entry'],manifest['health_path']) != ('digital-gallery','数字展馆协作空间','source','NODE_ESM','app.mjs','/health'):
                raise ValueError('manifest values')
            files=manifest['files']
            if not isinstance(files,list) or not 1<=len(files)<=512 or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.(mjs|json|html|css|svg)',x) for x in files) or len(set(files))!=len(files) or manifest['entry'] not in files:
                raise ValueError('manifest files')
        elif set(manifest) != _MANIFEST_FIELDS or manifest != _EXPECTED_MANIFEST:
            raise ValueError('manifest values')
        source = (resolved / manifest['source_root']).resolve(strict=True)
        source.relative_to(resolved)
        if not source.is_dir() or source.is_symlink():
            raise ValueError('source root')
        if node:
            if set(files)!={item.name for item in source.iterdir()} or any(not (source/name).is_file() or (source/name).stat().st_size>2*1024*1024 for name in files):
                raise ValueError('source files')
        else:
            module_path = source.joinpath(*manifest['entry_module'].split('.')).with_suffix('.py')
            if not module_path.is_file() or module_path.is_symlink():
                raise ValueError('entry module')
        _reject_symlinks(source)
        return OfficialSampleInstallation(
            available=True,
            root=resolved,
            source=source,
            sample_id=manifest["sample_id"],display_name=manifest["display_name"],
            runtime_kind="NODE_ESM" if node else "PYTHON",entry=manifest.get("entry"),files=tuple(manifest.get("files",())),
            entry_module=manifest.get("entry_module"),
            health_path=manifest["health_path"],
        )
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return OfficialSampleInstallation(
            available=False,
            reason="官方示例安装不完整或无效",
        )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate manifest key")
        result[key] = value
    return result


def _reject_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("sample symlink")


def _copy_source(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(source, destination, copy_function=shutil.copy2)
    except OSError as exc:
        raise JiejianError(
            ErrorCode.OFFICIAL_SAMPLE_START_FAILED,
            "官方示例源码复制失败",
        ) from exc
