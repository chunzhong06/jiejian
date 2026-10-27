# 文档必须能独立定位现有行为和源码，不将临时审计材料作为设计说明。
from pathlib import Path
from scripts.docs.checks import check_documents
from scripts.docs.generate import generate
from scripts.docs.markdown import heading_ids
import pytest

ROOT=Path(__file__).resolve().parents[2]

def test_current_documents_are_self_contained():
    assert check_documents(ROOT)==[]

def test_generated_reference_matches_current_declarations():
    assert generate(ROOT)==[]


def test_protocol_reference_exposes_declared_root_versions_without_inventing_component_versions(tmp_path):
    import json
    from scripts.docs.sources import schemas
    protocols=tmp_path/'product/protocols'
    directory=protocols/'schemas'
    directory.mkdir(parents=True)
    (protocols/'schema.py').write_text("SCHEMA_REGISTRY = (SchemaEntry('root.schema.json', 'owner:Root'), SchemaEntry('component.schema.json', 'owner:Component'))",encoding='utf-8')
    (directory/'root.schema.json').write_text(json.dumps({'properties':{'schema_version':{'const':'next'}}}),encoding='utf-8')
    (directory/'component.schema.json').write_text('{}',encoding='utf-8')
    assert schemas(tmp_path)==[('component.schema.json','owner:Component',()),('root.schema.json','owner:Root',('next',))]

def test_broken_local_link_is_reported(tmp_path):
    (tmp_path/'docs').mkdir()
    (tmp_path/'README.md').write_text('[不存在](docs/missing.md)',encoding='utf-8')
    (tmp_path/'docs/llms.txt').write_text('docs/missing.md',encoding='utf-8')
    failures=check_documents(tmp_path)
    assert any('无效本地链接' in item for item in failures)
    assert any('无效任务路由' in item for item in failures)

@pytest.mark.parametrize('body,valid',[
    ('[跳转](docs/target.md#章节)',True),
    ('[跳转](docs/target.md#章节-1)',True),
    ('[跳转](docs/target.md#缺失)',False),
    ('~~~md\n[示例](missing.md)\n~~~',True),
    ('`[示例](missing.md)`',True),
    ('[跳转][目标]\n\n[目标]: docs/target.md#章节',True),
    ('[跳转][未定义]',False),
])
def test_links_validate_real_dependencies_and_ignore_code_examples(tmp_path,body,valid):
    (tmp_path/'docs').mkdir()
    (tmp_path/'README.md').write_text(body,encoding='utf-8')
    (tmp_path/'docs/llms.txt').write_text('docs/target.md',encoding='utf-8')
    (tmp_path/'docs/target.md').write_text('# 章节\n\n## 章节\n',encoding='utf-8')
    assert (check_documents(tmp_path)==[]) is valid

def test_heading_anchors_support_chinese_and_duplicate_titles():
    assert heading_ids('# 正常访问\n## `账号` 与资源\n# 正常访问')=={'正常访问','账号-与资源','正常访问-1'}


def test_literal_source_references_follow_actual_owners_but_examples_are_not_dependencies(tmp_path):
    (tmp_path/'docs').mkdir()
    (tmp_path/'docs/llms.txt').write_text('',encoding='utf-8')
    source=tmp_path/'product/owner.py'
    source.parent.mkdir();source.write_text('# 真实源码。',encoding='utf-8')
    readme=tmp_path/'README.md'
    readme.write_text('定位 `product/owner.py::symbol`。\n```text\n`product/example.py`\n```',encoding='utf-8')
    assert check_documents(tmp_path)==[]
    source.rename(source.with_name('renamed.py'))
    assert any('无效源码引用' in value for value in check_documents(tmp_path))
