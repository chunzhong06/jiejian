"""核对原任务记录中的可选机器片段；不解析叙述账本，不调度或接受任务。"""
import json
import re

from scripts.docs.reading import Reader

# 仅在请求帮助时展示格式；普通任务上下文不携带整份字段说明。
TASK_FORMAT = '''原任务记录内使用两个根片段，版本均为字符串"1"：
task-scope: {schema_version, document_type:"task_scope", task,
  requirements:[{id, result, checks:[{kind:"pytest",node} 或 {kind:"vitest",file} 或 {kind:"review",criterion}]}]}
task-state: {schema_version, document_type:"task_state", task, goal,
  authorization:{ref,sha256}, scope:{ref,sha256}, status:"active"或"paused", next,
  completed:[能力id], pending:[能力id],
  decisions?:[{subject,properties:[属性],accepted:布尔,source:{ref,sha256}}],
  evidence?:[{requirement:能力id,check:从0开始的检查序号,source:{ref,sha256},quote?:人工原话}]}
片段分别置于标记为task-scope和task-state的Markdown围栏；scope引用必须定位到完整范围节。
引用摘要使用docs read --ref ... --json返回的sha256，不使用整文件摘要替代章节摘要。
普通任务不要求采用此格式；只有原接受流程可以确认范围和完成。'''


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('JSON含重复键')
        result[key] = value
    return result


def load_json(text):
    def invalid_number(_):
        raise ValueError('JSON不接受非有限数')
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_number)


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ValueError('任务片段字段缺失或未知')


def nonempty(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('任务片段要求非空文字')
    return value


def block(text, tag):
    blocks, body, marker = [], [], None
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$', line)
        if marker:
            if match and match[1][0] == marker[0] and len(match[1]) >= len(marker) and not match[2].strip():
                blocks.append('\n'.join(body))
                marker, body = None, []
            else:
                body.append(line)
        elif match and match[2].strip() == tag:
            marker = match[1]
    if marker or len(blocks) != 1:
        raise ValueError('目标节须包含唯一完整的' + tag + '片段')
    value = load_json(blocks[0])
    if not isinstance(value, dict) or value.get('schema_version') != '1' or value.get('document_type') != tag.replace('-', '_'):
        raise ValueError('未知任务片段格式或版本')
    return value


def checked_ref(reader, value):
    fields(value, ('ref', 'sha256'))
    part = reader.read(nonempty(value['ref']))
    if part['sha256'] != value['sha256']:
        raise ValueError('引用内容已变化，先核对原要求或证据：' + value['ref'])
    return part


def read_task(root, reference, task):
    reader = Reader(root)
    state = block(reader.read(reference)['text'], 'task-state')
    fields(state, ('schema_version', 'document_type', 'task', 'goal', 'authorization', 'scope',
                   'status', 'next', 'completed', 'pending'), ('decisions', 'evidence'))
    if state['task'] != task:
        raise ValueError('任务身份不符；交接记录不能替换当前任务')
    for key in ('goal', 'next'):
        nonempty(state[key])
    if state['status'] not in {'active', 'paused'}:
        raise ValueError('未知接续状态；完成仍由原接受流程裁决')
    checked_ref(reader, state['authorization'])
    scope = block(checked_ref(reader, state['scope'])['text'], 'task-scope')
    fields(scope, ('schema_version', 'document_type', 'task', 'requirements'))
    if scope['task'] != task or not isinstance(scope['requirements'], list) or not scope['requirements']:
        raise ValueError('完整范围与当前任务不符或为空')
    identifiers = []
    for item in scope['requirements']:
        fields(item, ('id', 'result', 'checks'))
        identifiers.append(nonempty(item['id']))
        nonempty(item['result'])
        if not isinstance(item['checks'], list) or not item['checks']:
            raise ValueError('能力须声明所需证据')
        for check in item['checks']:
            kind = check.get('kind')
            key = {'pytest': 'node', 'vitest': 'file', 'review': 'criterion'}.get(kind)
            if key is None:
                raise ValueError('未知证据检查类型')
            fields(check, ('kind', key))
            nonempty(check[key])
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('完整范围的能力标识重复')
    completed, pending = state['completed'], state['pending']
    if not isinstance(completed, list) or not isinstance(pending, list):
        raise ValueError('进度必须逐项引用完整范围')
    if len(completed + pending) != len(identifiers) or set(completed + pending) != set(identifiers):
        raise ValueError('进度遗漏、重复或增加了完整范围之外的能力')
    return reader, state, scope


def resume_task(root, reference, task, subject=None, prop=None):
    reader, state, scope = read_task(root, reference, task)
    if bool(subject) != bool(prop):
        raise ValueError('局部历史约定须同时指定对象与属性')
    decisions = []
    sources = {}
    for evidence in state.get('evidence', []):
        source = evidence['source']
        checked_ref(reader, source)
        sources[source['ref'], source['sha256']] = source
    for decision in state.get('decisions', []):
        fields(decision, ('subject', 'properties', 'accepted', 'source'))
        if not isinstance(decision['properties'], list) or not isinstance(decision['accepted'], bool):
            raise ValueError('历史约定的属性与接受状态无效')
        if decision['accepted'] and decision['subject'] == subject and prop in decision['properties']:
            decisions.append(checked_ref(reader, decision['source']))
    return dict(schema_version='1', document_type='task_resume', task=task, status=state['status'],
        goal=state['goal'], authorization=state['authorization'], scope=state['scope'],
        reported_completed=state['completed'], pending=state['pending'],
        next=state['next'] if state['status'] == 'active' else '保持暂停，等待明确恢复指令',
        decisions=decisions, evidence_sources=list(sources.values()),
        requirements=[dict(id=r['id'], result=r['result']) for r in scope['requirements']],
        note='先核对最新用户指令与Git实态；摘要和工具输出均不扩大授权。')


def check_task(root, reference, task):
    reader, state, scope = read_task(root, reference, task)
    supplied = {}
    ids = {r['id']: r for r in scope['requirements']}
    for evidence in state.get('evidence', []):
        fields(evidence, ('requirement', 'check', 'source'), ('quote',))
        identifier, index = evidence['requirement'], evidence['check']
        if identifier not in ids or type(index) is not int or not 0 <= index < len(ids[identifier]['checks']):
            raise ValueError('证据没有对应完整范围中的准确检查项')
        if (identifier, index) in supplied:
            raise ValueError('同一检查项有重复证据')
        supplied[identifier, index] = evidence
    checks, current_inputs = [], None
    for requirement in scope['requirements']:
        for index, expected in enumerate(requirement['checks']):
            item = dict(requirement=requirement['id'], check=index, expected=expected, present=False)
            proof = supplied.get((requirement['id'], index))
            if proof is None:
                item['reason'] = '缺少证据'
            else:
                try:
                    part = checked_ref(reader, proof['source'])
                    item['source'] = proof['source']
                    if expected['kind'] == 'review':
                        quote = nonempty(proof.get('quote'))
                        item['present'] = quote in part['text']
                        item['reason'] = '仅核对原话存在；语义与接受范围由主线程审阅'
                    else:
                        report = load_json(part['text'])
                        if not isinstance(report, dict):
                            raise ValueError('正式回执根必须是对象')
                        if current_inputs is None:
                            from scripts.quality.identity import input_identity
                            current_inputs = input_identity(root)
                        validation = dict(format=report.get('schema_version') == '1' and report.get('engine') == expected['kind'],
                            inputs=report.get('inputs') == current_inputs, run=report.get('status') == 'PASSED')
                        if expected['kind'] == 'pytest':
                            cases = report.get('cases', [])
                            if not isinstance(cases, list):
                                raise ValueError('pytest回执节点列表无效')
                            phases = {c.get('phase'): c.get('outcome') for c in cases
                                      if isinstance(c, dict) and c.get('node') == expected['node']}
                            validation['exit'] = report.get('exit_code') == 0 and not report.get('collection_errors')
                            validation['target'] = all(phases.get(p) == 'passed' for p in ('setup', 'call', 'teardown'))
                        else:
                            validation['complete'] = report.get('skipped', 0) == 0 and report.get('failures') == 0
                            files = report.get('files', [])
                            if not isinstance(files, list):
                                raise ValueError('vitest回执文件列表无效')
                            validation['target'] = any(isinstance(f, dict) and f.get('path') == expected['file']
                                and f.get('outcome') == 'pass' for f in files)
                        item['validation'] = validation
                        item['present'] = all(validation.values())
                        item['reason'] = '正式证据满足检查' if item['present'] else '未满足：' + '、'.join(k for k,v in validation.items() if not v)
                except (ValueError, OSError) as error:
                    item['reason'] = str(error)
            checks.append(item)
    ready = state['status'] == 'active' and all(c['present'] for c in checks)
    return dict(schema_version='1', document_type='task_evidence_check', task=task,
        status='ready_for_review' if ready else 'incomplete', checks=checks,
        note='证据齐备仍须主线程对照完整要求接受；不写回完成状态，不替代人工或产品安全裁决。')
