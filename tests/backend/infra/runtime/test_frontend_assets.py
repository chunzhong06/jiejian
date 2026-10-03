# 验证服务读取真实静态资源身份；缺失、损坏与目录外引用不冒充当前构建。
import hashlib
import json

import pytest

from product.backend.infra.runtime.frontend_assets import frontend_asset_identity
from product.protocols.runtime.frontend_assets import FrontendAssetManifest


def write_frontend(root):
    root.mkdir()
    (root/'assets').mkdir()
    data = {'index.html': '<html>app</html>', 'assets/index-12345678.js': 'export const app = true'}
    for name, text in data.items():
        (root/name).write_text(text, encoding='utf8')
    manifest = {'schema_version': '1', 'build_id': 'a'*64,
        'assets': [{'path': name, 'sha256': hashlib.sha256(text.encode()).hexdigest()} for name, text in data.items()]}
    (root/'frontend-manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    return manifest


def test_identity_is_confirmed_only_when_served_bytes_match(tmp_path):
    root=tmp_path/'frontend';write_frontend(root)
    assert frontend_asset_identity(root)['build_id']=='a'*64
    (root/'assets/index-12345678.js').write_text('changed',encoding='utf8')
    result=frontend_asset_identity(root)
    assert result['status']=='UNCONFIRMED' and result['build_id'] is None
    assert '不一致' in result['reason']


@pytest.mark.parametrize('update',[
    {'schema_version':'2'}, {'secret':'must-not-be-returned'},
    {'assets':[{'path':'../outside','sha256':'a'*64}]},
    {'assets':[{'path':'/outside','sha256':'a'*64}]},
    {'assets':[{'path':'index.html','sha256':'a'*64}]*2},
    {'build_id':'not-a-digest'},
])
def test_unknown_or_unsafe_manifest_is_not_a_verified_version(tmp_path,update):
    root=tmp_path/'frontend';manifest=write_frontend(root);manifest.update(update)
    (root/'frontend-manifest.json').write_text(json.dumps(manifest),encoding='utf8')
    result=frontend_asset_identity(root)
    assert result=={'status':'UNCONFIRMED','build_id':None,'reason':'前端资源身份尚未确认'}
    assert 'must-not-be-returned' not in json.dumps(result)


def test_missing_manifest_does_not_claim_up_to_date(tmp_path):
    assert frontend_asset_identity(None)['status']=='UNCONFIRMED'
    assert frontend_asset_identity(tmp_path)['status']=='UNCONFIRMED'


def test_duplicate_manifest_fields_are_not_silently_overwritten(tmp_path):
    root=tmp_path/'frontend';manifest=write_frontend(root)
    raw=json.dumps(manifest).replace('"schema_version": "1"', '"schema_version": "2", "schema_version": "1"')
    (root/'frontend-manifest.json').write_text(raw,encoding='utf8')
    assert frontend_asset_identity(root)['status']=='UNCONFIRMED'


def test_manifest_is_an_independent_root_with_unversioned_asset_members(tmp_path):
    root=tmp_path/'frontend';value=write_frontend(root)
    manifest=FrontendAssetManifest.model_validate_json(json.dumps(value))
    assert manifest.schema_version=='1'
    assert all('schema_version' not in member for member in manifest.model_dump(mode='json')['assets'])
