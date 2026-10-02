# 从实际服务目录核对静态构建身份；缺失或损坏时仅返回未知，不访问目录外的文件。
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from product.protocols.frontend_assets import FrontendAssetManifest


def _unique_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate frontend manifest key')
        result[key] = value
    return result


def frontend_asset_identity(directory: Path | None) -> dict:
    unavailable = dict(status='UNCONFIRMED', build_id=None, reason='前端资源身份尚未确认')
    if directory is None:
        return unavailable
    try:
        root = Path(directory).resolve()
        manifest_path = root/'frontend-manifest.json'
        if not manifest_path.resolve().is_relative_to(root) or manifest_path.stat().st_size > 131072:
            return unavailable
        with manifest_path.open('rb') as handle:
            raw = handle.read(131073)
        if len(raw) > 131072:
            return unavailable
        parsed = json.loads(raw, object_pairs_hook=_unique_members)
        manifest = FrontendAssetManifest.model_validate_json(json.dumps(parsed, allow_nan=False))
        total = 0
        for item in manifest.assets:
            path = (root/item.path).resolve()
            if not path.is_relative_to(root):
                return unavailable
            size = path.stat().st_size
            total += size
            if size > 16*1024*1024 or total > 64*1024*1024:
                return unavailable
            with path.open('rb') as handle:
                content = handle.read(16*1024*1024+1)
            if len(content) > 16*1024*1024 or hashlib.sha256(content).hexdigest() != item.sha256:
                return dict(status='UNCONFIRMED', build_id=None, reason='静态资源与构建清单不一致，请重新准备前端资源')
        return dict(status='CONFIRMED', build_id=manifest.build_id, reason='当前服务目录中的资源已核对')
    except (OSError, ValueError, ValidationError, RecursionError):
        return unavailable
