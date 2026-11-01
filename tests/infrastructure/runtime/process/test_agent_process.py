import json
import tomllib
from queue import Queue
from threading import Event

from product.backend.infrastructure.runtime import agent_process


class ProtocolProcess:
    """按客户端请求响应，旧回合完成通知用于检查续接时的归属。"""
    def __init__(self):
        self.lines = Queue()
        self.messages = []
        self.stdout = self.stdin = self

    def reply(self, value):
        self.lines.put(json.dumps(value) + '\n')

    def readline(self, limit):
        return self.lines.get(timeout=3)

    def flush(self):
        pass

    def write(self, line):
        value = json.loads(line)
        self.messages.append(value)
        if value.get('method') == 'initialize':
            self.reply(dict(id=1, result={}))
        elif value.get('method') in ('thread/start', 'thread/resume'):
            self.reply(dict(id=2, result={'thread': {'id': 'session'}}))
            self.reply(dict(method='turn/completed', params={'threadId': 'session', 'turn': {'id': 'old', 'status': 'completed'}}))
        elif value.get('method') == 'turn/start':
            self.reply(dict(id=3, result={'turn': {'id': 'current'}}))
            self.reply(dict(id=20, method='item/commandExecution/requestApproval', params={}))
        elif value.get('id') == 20:
            self.reply(dict(method='turn/completed', params={'threadId': 'session', 'turn': {'id': 'current', 'status': 'completed'}}))


def invoke(monkeypatch, *, cancelled=None, read_only=False):
    process, spawned, released, events = ProtocolProcess(), [], [], []
    monkeypatch.setattr(agent_process, 'spawn_managed_process', lambda command, **options: spawned.append((command, options)) or process)
    def terminate(value, timeout):
        released.append(value)
        value.lines.put('')
    monkeypatch.setattr(agent_process, 'terminate_process_tree', terminate)
    monkeypatch.setenv('OPENAI_API_KEY', 'fixture-private-provider-setting')
    result = agent_process.run_codex(executable='codex', cwd='current-project', profile='profile',
        connector='connector.py', python='python', prompt='only current task', session_id='session',
        allow_changes=False, read_only=read_only, cancelled=cancelled or Event(), on_event=lambda kind, data: events.append((kind, data)), timeout_seconds=3)
    return process, spawned, released, events, result


def test_resume_keeps_current_turn_and_declines_native_escalation(monkeypatch):
    process, spawned, released, events, result = invoke(monkeypatch)
    assert result == dict(state='FINISHED', session_id='session', restricted=True, failed_tools=False, tool_calls=[])
    assert any(item.get('method') == 'turn/start' for item in process.messages)
    turn = next(item for item in process.messages if item.get('method') == 'turn/start')
    assert turn['params']['sandboxPolicy'] == {'type': 'readOnly', 'networkAccess': False}
    assert next(item for item in process.messages if item.get('id') == 20)['result'] == {'decision': 'decline'}
    assert 'OPENAI_API_KEY' not in spawned[0][1]['env']
    assert released == [process]
    assert ('RESTRICTED', None) in events
    config = tomllib.loads(spawned[0][0][-1])['mcp_servers']['jiejian']
    assert config['required'] and config['default_tools_approval_mode'] == 'writes'
    assert config['tools']['jiejian_collaboration_action']['approval_mode'] == 'approve'
    assert 'jiejian_collaboration_control' not in config['enabled_tools']


def test_cancel_before_turn_never_starts_inference_and_releases_process(monkeypatch):
    cancelled = Event(); cancelled.set()
    process, _, released, _, result = invoke(monkeypatch, cancelled=cancelled)
    assert result['state'] == 'INTERRUPTED'
    assert not any(item.get('method') == 'turn/start' for item in process.messages)
    assert released == [process]


def test_read_only_executor_never_exposes_mutating_gateway(monkeypatch):
    _, spawned, _, _, _ = invoke(monkeypatch, read_only=True)
    parsed = tomllib.loads(spawned[0][0][-1])['mcp_servers']['jiejian']
    assert set(parsed['enabled_tools']) == {'jiejian_collaboration_read',
        'jiejian_collaboration_context', 'jiejian_collaboration_capability'}
    assert parsed['tools'] == {}
