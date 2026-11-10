# 文档必须能独立定位现有行为和源码，不将临时审计材料作为设计说明。
from pathlib import Path
from scripts.docs.checks import check_documents
from scripts.docs.generate import generate,module_page
from scripts.docs.markdown import heading_ids,link_targets
import pytest

ROOT=Path(__file__).resolve().parents[2]


def test_module_index_keeps_production_testing_pages_and_content_invalidates_parse_cache(tmp_path):
    from scripts.docs.sources import modules,routes
    directory=tmp_path/'product/frontend/src/pages/testing';directory.mkdir(parents=True)
    (directory/'Testing.tsx').write_text('export function Testing() {}',encoding='utf-8')
    (directory/'Testing.test.tsx').write_text('test fixture',encoding='utf-8')
    assert [item[0] for item in modules(tmp_path)]==['product/frontend/src/pages/testing/Testing.tsx']
    router=tmp_path/'product/backend/interfaces/http/routers/example.py';router.parent.mkdir(parents=True)
    router.write_text("@router.get('/before')\ndef read(): pass",encoding='utf-8')
    assert routes(tmp_path)[0][1]=='/before'
    router.write_text("@router.get('/after')\ndef read(): pass",encoding='utf-8')
    assert routes(tmp_path)[0][1]=='/after'

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


@pytest.mark.parametrize('route,valid',[
    ('[读取章节](target.md#章节)',True),
    ('[读取章节](target.md#不存在)',False),
    ('[读取章节](https://example.com/guide.md)',False),
    ('[读取章节](../README.md)',False),
    ('[](target.md#章节)',False),
    ('[   ](target.md#章节)',False),
    ('[读取章节](target.md#章节',False),
    ('[读取章节](missing.md#章节)',False),
    ('[读取章节](target.md#章节)\n[另一章](target.md#章节-1)',True),
    ('完整读取 → [存在](target.md#章节)、[失效](missing.md)',False),
    ('读取章节 → [章节](target.md#章节)',True),
    ('读取章节 → [章节](target.md#%E7%AB%A0%E8%8A%82)',True),
    ('读取章节 → [重复标题](target.md#章节-1)',True),
    ('读取章节 → [章节](target.md#不存在)',False),
    ('读取章节 → docs/target.md#章节',True),
    ('读取章节 → docs/target.md#不存在',False),
    ('读取章节 → [外部网页](https://example.com/guide.md)',False),
    ('读取章节 → [仓库外](../../outside.md)',False),
    ('读取章节 → [根说明](../README.md)',False),
    ('读取章节 → [根说明](%2e%2e/README.md)',False),
    ('读取章节 → [目录](.)',False),
    ('读取章节 → ',False),
    (' → [章节](target.md#章节)',False),
    ('~~~text\n示例 → [不存在](missing.md#不存在)\n~~~',True),
])
def test_task_routes_require_local_documents_and_existing_sections(tmp_path,route,valid):
    (tmp_path/'docs').mkdir()
    (tmp_path/'README.md').write_text('# 仓库说明',encoding='utf-8')
    (tmp_path/'docs/llms.txt').write_text(route,encoding='utf-8')
    (tmp_path/'docs/target.md').write_text('# 章节\n\n## 章节\n',encoding='utf-8')
    assert (check_documents(tmp_path)==[]) is valid


def test_module_reference_navigation_preserves_file_facts_and_distinguishes_heading_collisions():
    # 目录名去掉标点后可能相同，导航仍须对应各自章节。
    rows=[
        ('scripts/docs/__init__.py',1,[]),
        ('scripts/docs/helpers/a.b/read.py',12,['read']),
        ('scripts/docs/helpers/ab/write.py',18,['write','publish']),
    ]
    page=module_page('scripts',rows)
    assert '[docs/helpers/a.b](#docshelpersab)' in page
    assert '[docs/helpers/ab](#docshelpersab-1)' in page
    targets,missing=link_targets(page)
    assert not missing
    assert all(target[1:] in heading_ids(page) for target in targets if target.startswith('#'))
    for file,lines,names in rows:
        assert f'### {Path(file).relative_to("scripts").as_posix()}' in page
        assert page.count(f'[源码](../../../{file})（{lines} 行）')==1
        assert all(f'`{name}`' in page for name in names)
