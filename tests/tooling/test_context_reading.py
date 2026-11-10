"""验证实际读取边界、接续身份与正式证据接受；不以规范字串替代行为。"""
import json
from pathlib import Path

import pytest

from scripts.docs.context import main, page_text
from scripts.docs.reading import Reader, digest, read_context
from scripts.docs.task_records import check_task, load_json, resume_task
from scripts.quality.identity import input_identity


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def pointer(root, ref):
    return dict(ref=ref, sha256=Reader(root).read(ref)['sha256'])


def section(value, tag):
    return '```' + tag + '\n' + json.dumps(value, ensure_ascii=False) + '\n```\n'


def task_record(root, *, status='active'):
    scope = dict(schema_version='1', document_type='task_scope', task='original', requirements=[
        dict(id='core', result='核心链', checks=[dict(kind='pytest', node='tests/test_flow.py::test_core')]),
        dict(id='transition', result='真实撤回与复测', checks=[dict(kind='pytest', node='tests/test_flow.py::test_transition')])])
    scope_text = '# 原始任务\n\n## 完整范围\n用户要求核心链及真实撤回与复测。\n' + section(scope, 'task-scope')
    # 先固定章节边界再取摘要；后续更新状态不会改变完整范围末尾的空行。
    write(root, 'var/task.md', scope_text + '\n## 当前状态\n')
    write(root, 'var/authorization.md', '# 当前指令\n\n只继续原任务，局部接受颜色。\n')
    state = dict(schema_version='1', document_type='task_state', task='original', goal='完成原任务',
        authorization=pointer(root, 'var/authorization.md'), scope=pointer(root, 'var/task.md#完整范围'),
        status=status, next='补齐真实状态转换', completed=['core'], pending=['transition'], decisions=[], evidence=[])
    save_state(root, scope_text, state)
    return scope_text, state


def save_state(root, scope_text, state):
    write(root, 'var/task.md', scope_text + '\n## 当前状态\n' + section(state, 'task-state'))


def proof(root, node='tests/test_flow.py::test_core', *, outcome='passed', inputs=None):
    report = dict(schema_version='1', engine='pytest', status='PASSED', exit_code=0,
        inputs=input_identity(root) if inputs is None else inputs, collection_errors=[],
        cases=[dict(node=node, phase=phase, outcome=outcome) for phase in ('setup', 'call', 'teardown')])
    write(root, 'var/proof.json', json.dumps(report))
    return pointer(root, 'var/proof.json')


def test_semantic_read_keeps_preface_children_and_stops_at_peer_not_fenced_heading(tmp_path):
    write(tmp_path, 'docs/llms.txt', '[查询](owner.md#目标)\n')
    write(tmp_path, 'docs/owner.md', '# 契约\n\n前提必须保留\n\n## 目标\n正文\n```md\n## 假标题\n```\n### 子节\n失败路径\n## 未解锁\n其他任务\n')
    result = read_context(tmp_path, routes=['查询'])
    text = result['passages'][0]['text']
    assert '前提必须保留' in text and '失败路径' in text and '假标题' in text
    assert '其他任务' not in text


def test_implementation_expands_entire_owner_and_development_merges_duplicate_routes(tmp_path):
    write(tmp_path, 'docs/llms.txt', '[查询](owner.md#版本)\n跨边界 → [一](owner.md#版本)、[二](other.md)\n')
    write(tmp_path, 'docs/owner.md', '# 契约\n## 版本\n版本\n## 失败与秘密\n拒绝条件\n')
    write(tmp_path, 'docs/other.md', '# 第二契约\n其他边界\n')
    write(tmp_path, 'docs/工程/开发.md', '# 开发\n正式入口\n')
    result = read_context(tmp_path, routes=['查询', '跨边界'], implement=True)
    assert len(result['passages']) == 3
    assert '拒绝条件' in result['passages'][0]['text']
    assert result['selected_owners_full'] is True


def test_same_context_receipt_reuses_only_unchanged_input(tmp_path):
    write(tmp_path, 'docs/llms.txt', '[查询](owner.md#目标)\n')
    path = write(tmp_path, 'docs/owner.md', '# 契约\n## 目标\n原条件\n')
    first = read_context(tmp_path, routes=['查询'])
    assert read_context(tmp_path, routes=['查询'], seen=first['receipts'])['content_chars'] == 0
    assert read_context(tmp_path, routes=['查询'])['content_chars'] > 0
    path.write_text('# 契约\n## 目标\n条件变化\n', encoding='utf-8')
    assert '条件变化' in read_context(tmp_path, routes=['查询'], seen=first['receipts'])['passages'][0]['text']


@pytest.mark.parametrize('ref', ['../outside.md', 'https://example.com/a.md', 'scripts/dev.ps1', '.git/config', 'docs/missing.md'])
def test_invalid_or_non_document_reference_is_rejected(tmp_path, ref):
    with pytest.raises(ValueError):
        Reader(tmp_path).read(ref)


def test_large_document_is_rejected_without_silent_truncation(tmp_path):
    write(tmp_path, 'docs/big.md', 'x' * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match='不输出截断'):
        Reader(tmp_path).read('docs/big.md')


def test_source_query_keeps_static_limit_and_exact_file_without_directory_table(tmp_path):
    write(tmp_path, 'docs/llms.txt', '[查询模块](参考/模块索引.md)\n')
    write(tmp_path, 'docs/参考/模块索引.md', '# 索引\n\n不表示运行验收\n\n| 范围 | 数量 | 分册 |\n| `product/backend/application` | 9 | [查看声明](模块/app.md) |\n')
    write(tmp_path, 'docs/参考/模块/app.md', '# 分册\n目录很长\n## checks\n### checks/reading/a.py\n公开声明：A、B\n### checks/reading/b.py\n其他声明\n')
    result = read_context(tmp_path, routes=['查询模块'], source='product/backend/application/checks/reading/a.py')
    text = ''.join(p['text'] for p in result['passages'])
    assert '不表示运行验收' in text and '公开声明：A、B' in text
    assert '其他声明' not in text and '| 范围' not in text and '目录很长' not in text
    with pytest.raises(ValueError, match='不能代替实施'):
        read_context(tmp_path, source='product/backend/application/checks/reading/a.py', implement=True)


def test_scoped_memory_returns_only_accepted_matching_object_and_property(tmp_path):
    original, state = task_record(tmp_path)
    write(tmp_path, 'var/colors.md', '# 颜色\n只采用颜色\n')
    write(tmp_path, 'var/fonts.md', '# 字体\n旧字号建议\n')
    state['decisions'] = [
        dict(subject='视觉', properties=['配色'], accepted=True, source=pointer(tmp_path, 'var/colors.md')),
        dict(subject='视觉', properties=['字号'], accepted=False, source=pointer(tmp_path, 'var/fonts.md')),
        dict(subject='内容表', properties=['配色'], accepted=True, source=pointer(tmp_path, 'var/fonts.md'))]
    save_state(tmp_path, original, state)
    result = resume_task(tmp_path, 'var/task.md#当前状态', 'original', '视觉', '配色')
    assert len(result['decisions']) == 1 and '只采用颜色' in result['decisions'][0]['text']
    assert resume_task(tmp_path, 'var/task.md#当前状态', 'original')['decisions'] == []


def test_task_identity_and_pause_prevent_handoff_from_replacing_current_task(tmp_path):
    task_record(tmp_path, status='paused')
    result = resume_task(tmp_path, 'var/task.md#当前状态', 'original')
    assert result['next'] == '保持暂停，等待明确恢复指令'
    with pytest.raises(ValueError, match='任务身份不符'):
        resume_task(tmp_path, 'var/task.md#当前状态', 'new-handoff')


def test_scope_change_and_later_progress_summary_cannot_shrink_full_requirements(tmp_path):
    original, state = task_record(tmp_path)
    state['pending'] = []
    save_state(tmp_path, original, state)
    with pytest.raises(ValueError, match='进度遗漏'):
        resume_task(tmp_path, 'var/task.md#当前状态', 'original')
    save_state(tmp_path, original.replace('真实撤回与复测', '只有核心链'), state)
    with pytest.raises(ValueError, match='引用内容已变化'):
        resume_task(tmp_path, 'var/task.md#当前状态', 'original')


def test_completed_checkbox_does_not_substitute_for_real_transition_evidence(tmp_path):
    original, state = task_record(tmp_path)
    state['completed'], state['pending'] = ['core', 'transition'], []
    state['evidence'] = [dict(requirement='core', check=0, source=proof(tmp_path))]
    save_state(tmp_path, original, state)
    result = check_task(tmp_path, 'var/task.md#当前状态', 'original')
    assert result['status'] == 'incomplete'
    assert [c['present'] for c in result['checks']] == [True, False]


@pytest.mark.parametrize('variant', ['skipped', 'failed', 'wrong-node', 'old-inputs', 'tampered', 'wrong-version'])
def test_failed_skipped_stale_and_wrong_scope_proof_cannot_pass(tmp_path, variant):
    original, state = task_record(tmp_path)
    source = proof(tmp_path, outcome=variant if variant in {'skipped', 'failed'} else 'passed',
        node='tests/test_flow.py::test_terminal_only' if variant == 'wrong-node' else 'tests/test_flow.py::test_core',
        inputs={} if variant == 'old-inputs' else None)
    if variant == 'wrong-version':
        path = tmp_path / 'var/proof.json'
        document = json.loads(path.read_text('utf-8')); document['schema_version'] = 'unknown'
        path.write_text(json.dumps(document), encoding='utf-8'); source = pointer(tmp_path, 'var/proof.json')
    elif variant == 'tampered':
        (tmp_path / 'var/proof.json').write_text('{}', encoding='utf-8')
    state['evidence'] = [dict(requirement='core', check=0, source=source)]
    save_state(tmp_path, original, state)
    assert check_task(tmp_path, 'var/task.md#当前状态', 'original')['checks'][0]['present'] is False


def test_ready_evidence_still_returns_review_gate_and_does_not_modify_record(tmp_path):
    original, state = task_record(tmp_path)
    document = json.loads((tmp_path / proof(tmp_path)['ref']).read_text('utf-8'))
    document['cases'] += [dict(node='tests/test_flow.py::test_transition', phase=p, outcome='passed') for p in ('setup', 'call', 'teardown')]
    write(tmp_path, 'var/proof.json', json.dumps(document))
    state['evidence'] = [dict(requirement=name, check=0, source=pointer(tmp_path, 'var/proof.json')) for name in ('core', 'transition')]
    save_state(tmp_path, original, state)
    before = (tmp_path / 'var/task.md').read_bytes()
    assert check_task(tmp_path, 'var/task.md#当前状态', 'original')['status'] == 'ready_for_review'
    assert (tmp_path / 'var/task.md').read_bytes() == before


def test_reader_rejects_duplicate_json_keys():
    with pytest.raises(ValueError, match='重复键'):
        load_json('{"schema_version":"1","schema_version":"2"}')


def test_command_reports_incomplete_with_nonzero_exit_code(tmp_path, capsys):
    task_record(tmp_path)
    assert main(['--root', str(tmp_path), 'check-task', '--record', 'var/task.md#当前状态', '--task', 'original']) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'incomplete'


def test_vitest_requires_exact_file_and_rejects_skipped_or_stale_run(tmp_path):
    original, state = task_record(tmp_path)
    original = original.replace('"kind": "pytest", "node": "tests/test_flow.py::test_core"',
        '"kind": "vitest", "file": "src/Case.test.tsx"')
    save_state(tmp_path, original, state)
    state['scope'] = pointer(tmp_path, 'var/task.md#完整范围')
    report = dict(schema_version='1', engine='vitest', status='PASSED', failures=0, skipped=0,
        inputs=input_identity(tmp_path), files=[dict(path='src/Case.test.tsx', outcome='pass')])
    for skipped, expected in [(0, True), (1, False)]:
        report['skipped'] = skipped
        write(tmp_path, 'var/vitest.json', json.dumps(report))
        state['evidence'] = [dict(requirement='core', check=0, source=pointer(tmp_path, 'var/vitest.json'))]
        save_state(tmp_path, original, state)
        assert check_task(tmp_path, 'var/task.md#当前状态', 'original')['checks'][0]['present'] is expected


def test_review_keeps_exact_quote_and_only_mechanical_presence_is_checked(tmp_path):
    original, state = task_record(tmp_path)
    original = original.replace('"kind": "pytest", "node": "tests/test_flow.py::test_core"',
        '"kind": "review", "criterion": "布局接受"')
    save_state(tmp_path, original, state)
    state['scope'] = pointer(tmp_path, 'var/task.md#完整范围')
    write(tmp_path, 'var/review.md', '# 用户原话\n这三处布局已经接受，流程继续检查。\n')
    state['evidence'] = [dict(requirement='core', check=0, source=pointer(tmp_path, 'var/review.md'), quote='这三处布局已经接受')]
    save_state(tmp_path, original, state)
    result = check_task(tmp_path, 'var/task.md#当前状态', 'original')
    assert result['checks'][0]['present'] is True
    assert '语义与接受范围由主线程审阅' in result['checks'][0]['reason']
    assert result['status'] == 'incomplete'


@pytest.mark.parametrize('mutation', ['unknown-field', 'unknown-version'])
def test_task_record_has_strict_reader_instead_of_silent_defaults(tmp_path, mutation):
    original, state = task_record(tmp_path)
    if mutation == 'unknown-field':
        state['auto_approve'] = True
    else:
        state['schema_version'] = 'future'
    save_state(tmp_path, original, state)
    with pytest.raises(ValueError):
        resume_task(tmp_path, 'var/task.md#当前状态', 'original')


def test_source_suffix_is_resolved_only_when_unique(tmp_path):
    write(tmp_path, 'docs/llms.txt', '')
    write(tmp_path, 'docs/参考/模块索引.md', '# 索引\n静态限制\n| `product/backend/application` | 1 | [查看声明](模块/a.md) |\n| `product/backend/domain` | 1 | [查看声明](模块/d.md) |\n')
    write(tmp_path, 'docs/参考/模块/a.md', '# 分册\n### checks/a.py\n[源码](../../../product/backend/application/checks/a.py) 声明A\n')
    other = write(tmp_path, 'docs/参考/模块/d.md', '# 分册\n### other.py\n[源码](../../../product/backend/domain/other.py)\n')
    result = read_context(tmp_path, source='checks/a.py')
    assert '声明A' in result['passages'][-1]['text']
    other.write_text('# 分册\n### checks/a.py\n[源码](../../../product/backend/domain/checks/a.py)\n', encoding='utf-8')
    with pytest.raises(ValueError, match='不唯一'):
        read_context(tmp_path, source='checks/a.py')


def test_heading_anchor_case_does_not_require_another_search(tmp_path):
    write(tmp_path, 'docs/a.md', '# 指南\n## Windows 启动\n准确内容\n')
    assert '准确内容' in Reader(tmp_path).read('docs/a.md#Windows-启动')['text']


def test_pagination_reassembles_full_contract_and_rejects_stale_cursor():
    text = ''.join('## 第' + str(i) + '节\n' + '约束' * 100 + '\n\n' for i in range(20))
    cursor, parts = None, []
    while True:
        page = page_text(text, cursor, 300)
        assert len(page['text']) <= 300
        parts.append(page['text'])
        if page['complete']:
            break
        cursor = page['next_cursor']
    assert ''.join(parts) == text
    first = page_text(text, budget=300)
    with pytest.raises(ValueError, match='游标过期'):
        page_text(text + '来源变化', first['next_cursor'], 300)


def test_partial_json_never_returns_full_text_or_reusable_receipts(tmp_path, capsys):
    write(tmp_path, 'docs/llms.txt', '[查询](a.md)\n')
    write(tmp_path, 'docs/a.md', '# 指南\n' + '完整契约\n\n' * 200)
    assert main(['--root', str(tmp_path), 'read', '--route', '查询', '--max-chars', '256', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['page']['complete'] is False
    assert result['receipts'] == {} and result['passages'] == []
    assert len(result['page']['text']) <= 256


def test_non_object_evidence_is_a_gap_instead_of_a_traceback(tmp_path):
    original, state = task_record(tmp_path)
    write(tmp_path, 'var/bad.json', '[]')
    state['evidence'] = [dict(requirement='core', check=0, source=pointer(tmp_path, 'var/bad.json'))]
    save_state(tmp_path, original, state)
    result = check_task(tmp_path, 'var/task.md#当前状态', 'original')
    assert result['checks'][0]['present'] is False and '根必须是对象' in result['checks'][0]['reason']


def test_resume_preserves_deduplicated_evidence_entries_without_loading_report_into_output(tmp_path):
    original, state = task_record(tmp_path)
    source = proof(tmp_path)
    state['evidence'] = [dict(requirement=name, check=0, source=source) for name in ('core', 'transition')]
    save_state(tmp_path, original, state)
    result = resume_task(tmp_path, 'var/task.md#当前状态', 'original')
    assert result['scope'] == state['scope']
    assert result['evidence_sources'] == [source]
    assert 'cases' not in json.dumps(result)
