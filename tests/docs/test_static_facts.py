# 用独立反例验证静态参考不会把遗漏、嵌套版本或失效引用当成有效知识。
from pathlib import Path

import pytest

from scripts.docs.generate import generate, render
from scripts.docs.registrations import api_routes, mcp_tools, migration_rows, root_versions
from scripts.docs.sources import grouped_sources
from tests.docs.checks import check_documentation


def put(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def minimal(root):
    put(root, 'docs/llms.txt', '# 空夹具路由\n')
    return root


def test_new_source_domains_empty_packages_and_public_methods_are_indexed(tmp_path):
    root = minimal(tmp_path)
    expected = ['product/backend/composition/application.py', 'product/backend/infra/observers/records/__init__.py',
                'product/protocols/preparation/models.py', 'product/backend/infra/runtime/process/node.mjs',
                'scripts/editor/view.cjs', 'product/frontend/src/shared/style.css']
    for path in expected:
        put(root, path, '# 文件职责\n' if path.endswith('.py') else '// 文件职责\n')
    put(root, expected[0], 'raise RuntimeError("不能导入")\nclass Core:\n    def close(self): pass\n')
    actual = [p.relative_to(root).as_posix() for group in grouped_sources(root).values() for p in group]
    assert sorted(actual) == sorted(expected)
    assert len(actual) == len(set(actual))
    text = '\n'.join(render(root).values())
    assert 'Core.close(self)' in text
    assert all(path in text for path in expected)


def test_parse_failure_preserves_all_generated_files(tmp_path):
    root = minimal(tmp_path)
    source = put(root, 'product/backend/core/checks.py', 'def check(): pass\n')
    generate(root, True)
    before = {p: p.read_bytes() for p in (root / 'docs').rglob('*.md')}
    source.write_text('def broken(:', encoding='utf-8')
    with pytest.raises(SystemExit, match='源码解析失败'):
        generate(root, True)
    assert before == {p: p.read_bytes() for p in before}


def test_root_versions_do_not_include_nested_dto_versions():
    schema = {'oneOf': [{'$ref': '#/$defs/A'}, {'$ref': '#/$defs/B'}], '$defs': {
        'A': {'properties': {'schema_version': {'const': '3'}, 'nested': {'properties': {'schema_version': {'const': '99'}}}}},
        'B': {'properties': {'schema_version': {'const': '5'}}}}}
    assert root_versions(schema) == '3, 5'
    assert root_versions({'properties': {'nested': schema}}) == '无可静态确认的根版本'


def test_api_nested_registration_and_unmounted_declaration_are_distinct(tmp_path):
    put(tmp_path, 'product/backend/api/app.py', 'from product.backend.api.routes import build_router\ndef create_app():\n    app.include_router(build_router(ctx))\n')
    put(tmp_path, 'product/backend/api/routes.py', 'from product.backend.api.child import build_child\ndef build_router(ctx):\n    router.include_router(build_child(ctx))\ndef unused(ctx): pass\n')
    put(tmp_path, 'product/backend/api/child.py', 'def build_child(ctx): pass\n')
    rows = api_routes(tmp_path)
    assert len(rows) == 2
    assert any('build_child' in target for _, target, _ in rows)
    assert not any('unused' in target for _, target, _ in rows)
    put(tmp_path, 'product/backend/api/app.py', 'def create_app():\n    app.include_router(select_router())\n')
    assert api_routes(tmp_path)[0][2] == '未静态确定'


def test_mcp_collects_only_explicit_registration_helpers(tmp_path):
    put(tmp_path, 'product/backend/api/mcp/server.py', 'from product.backend.api.mcp.preparation import register_preparation\ndef build_mcp_control():\n    register_preparation(server)\n    @server.tool(name="visible")\n    def tool(): pass\ndef unused():\n    @server.tool(name="hidden")\n    def tool(): pass\n')
    put(tmp_path, 'product/backend/api/mcp/preparation.py', 'def register_preparation(server):\n    @server.tool(name="prepare")\n    def tool(): pass\n')
    assert [name for name, _ in mcp_tools(tmp_path)] == ['prepare', 'visible']


def test_migration_head_rejects_fork_and_disconnected_cycle_without_import(tmp_path):
    put(tmp_path, 'product/backend/infra/storage/db.py', 'raise RuntimeError("禁止打开数据库")\n_CURRENT_MIGRATION_REVISION="b"\n')
    put(tmp_path, 'product/backend/migrations/versions/a.py', 'revision="a"\ndown_revision=None\n')
    put(tmp_path, 'product/backend/migrations/versions/b.py', 'revision="b"\ndown_revision="a"\n')
    assert migration_rows(tmp_path)[1] == 'b'
    c = put(tmp_path, 'product/backend/migrations/versions/c.py', 'revision="c"\ndown_revision="a"\n')
    with pytest.raises(ValueError, match='唯一'):
        migration_rows(tmp_path)
    c.write_text('revision="c"\ndown_revision="d"\n', encoding='utf-8')
    put(tmp_path, 'product/backend/migrations/versions/d.py', 'revision="d"\ndown_revision="c"\n')
    with pytest.raises(ValueError, match='循环或不连通'):
        migration_rows(tmp_path)


def test_symbol_command_coordinates_and_adr_list_status(tmp_path):
    root = minimal(tmp_path)
    put(root, 'product/backend/core/current.py', 'class Current:\n    def read(self): pass\n')
    put(root, 'product/frontend/src/Panel.test.tsx', '// 测试位置\n')
    guide = put(root, 'docs/任务.md', '`product/backend/core/current.py::Current.read`\n```powershell\n.\\scripts\\dev.ps1 frontend-test src/Panel.test.tsx\n```\n')
    assert check_documentation(root) == []
    guide.write_text('`product/backend/core/current.py::Current.missing`\n```powershell\n.\\scripts\\dev.ps1 test tests/missing.py\n```\n', encoding='utf-8')
    errors = check_documentation(root)
    assert any('静态符号不存在' in e for e in errors)
    assert any('测试命令路径' in e for e in errors)
    put(root, 'docs/llms.txt', '→ docs/历史.md\n')
    put(root, 'docs/历史.md', '# 旧设计\n- 状态：已取代\n')
    assert any('非当前' in e for e in check_documentation(root))


def test_generator_refuses_nonmanaged_documents_and_cleans_obsolete_outputs(tmp_path):
    root = minimal(tmp_path)
    source = put(root, 'product/backend/core/sample.py', 'class Sample: pass\n')
    generate(root, True)
    old = root / 'docs/参考/生成/代码/backend/core/_root.md'
    assert old.exists()
    source.unlink()
    generate(root, True)
    assert not old.exists()
    assert not old.parent.exists()
    note = put(root, 'docs/参考/生成/manual.md', '# 人工内容\n')
    with pytest.raises(SystemExit, match='非受管'):
        generate(root, True)
    assert note.read_text(encoding='utf-8') == '# 人工内容\n'


def test_dynamic_test_arguments_are_reported_without_execution(tmp_path):
    root = minimal(tmp_path)
    put(root, 'docs/示例.md', '```powershell\n.\\scripts\\dev.ps1 test tests/<case>.py $selected ...\n```\n')
    notices = []
    assert check_documentation(root, notices=notices) == []
    assert len(notices) == 3
    assert any('$selected' in value for value in notices)
