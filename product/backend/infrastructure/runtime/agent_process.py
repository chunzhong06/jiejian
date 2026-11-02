from __future__ import annotations

import json
import os
import subprocess
import time
from queue import Empty, Full, Queue
from threading import Event, Thread
from product.backend import __version__

from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.process.tree import spawn_managed_process, terminate_process_tree


def run_codex(*, executable, cwd, profile, connector, python, prompt, session_id, allow_changes,
    cancelled, on_event, read_only=False, timeout_seconds=900):
    """只交换会话协议与有限进度；不保存模型原文、推理或子进程日志。"""
    read_tools = ['jiejian_collaboration_context', 'jiejian_collaboration_capability', 'jiejian_collaboration_read']
    delegated = ['jiejian_collaboration_action', 'jiejian_collaboration_question', 'jiejian_collaboration_receipt']
    config = dict(jiejian=dict(command=python, args=['-B', connector, '--profile', profile],
        enabled_tools=read_tools if read_only else read_tools + delegated,
        tools={} if read_only else {name: dict(approval_mode='approve') for name in delegated}))
    command = [executable, 'app-server', '--listen', 'stdio://', '-c', 'mcp_servers=' + _toml_servers(config)]
    environment = {key: value for key, value in os.environ.items() if key.upper() in {
        'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'PATH', 'TEMP', 'TMP', 'USERPROFILE',
        'APPDATA', 'LOCALAPPDATA', 'HOMEDRIVE', 'HOMEPATH', 'CODEX_HOME'}}
    process = spawn_managed_process(command, cwd=cwd, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding='utf-8', errors='strict', bufsize=1)
    # 管道读取与协议状态机分开；有界队列限制客户端突发事件占用的内存。
    incoming = Queue(maxsize=128)
    closed = Event()
    def deliver(value):
        # 消费者退出后释放生产者，避免事件突发填满队列时遗留阻塞的管道线程。
        while not closed.is_set():
            try:
                incoming.put(value, timeout=.1)
                return
            except Full:
                pass
    def read():
        try:
            for line in iter(lambda: process.stdout.readline(1_048_577), ''):
                if len(line) > 1_048_576:
                    return
                deliver(json.loads(line))
        except (OSError, ValueError, UnicodeError):
            pass
        finally:
            deliver(None)
    reader = Thread(target=read, name='jiejian-agent-protocol', daemon=True)
    def send(value):
        process.stdin.write(json.dumps(value, ensure_ascii=False) + '\n'); process.stdin.flush()
    started, turn_id, interrupted = time.monotonic(), None, False
    interrupted_at = None
    restricted, failed_tools, tool_calls = False, False, []
    try:
        reader.start()
        send(dict(id=1, method='initialize', params=dict(clientInfo=dict(name='jiejian', title='界鉴', version=__version__))))
        while time.monotonic() - started < timeout_seconds:
            if cancelled.is_set():
                if turn_id and not interrupted:
                    send(dict(id=9, method='turn/interrupt', params=dict(threadId=session_id, turnId=turn_id)))
                    interrupted = True
                    interrupted_at = time.monotonic()
                elif not turn_id:
                    return dict(state='INTERRUPTED', session_id=session_id)
            if interrupted_at is not None and time.monotonic() - interrupted_at > 3:
                # 协议取消迟迟未结束时，仅释放本次受控进程树，不继续等待模型回合。
                return dict(state='INTERRUPTED', session_id=session_id)
            try: message = incoming.get(timeout=0.2)
            except Empty: continue
            if message is None:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, 'Agent 协议连接已断开，原任务保留')
            if 'error' in message:
                raise JiejianError(ErrorCode.STATE_PRECONDITION, 'Agent 未能接受本次请求，请核对客户端或账号状态')
            if message.get('id') == 1 and 'result' in message:
                send(dict(method='initialized'))
                params = dict(cwd=cwd, approvalPolicy='on-request',
                    sandbox='workspace-write' if allow_changes else 'read-only')
                if session_id: params['threadId'] = session_id
                send(dict(id=2, method='thread/resume' if session_id else 'thread/start', params=params))
                on_event('CONNECTED', None)
            elif message.get('id') == 2 and 'result' in message:
                session_id = message['result']['thread']['id']
                on_event('SESSION', session_id)
                sandbox = dict(type='workspaceWrite', writableRoots=[cwd], networkAccess=False,
                    excludeSlashTmp=True, excludeTmpdirEnvVar=True) if allow_changes else dict(type='readOnly', networkAccess=False)
                send(dict(id=3, method='turn/start', params=dict(threadId=session_id,
                    input=[dict(type='text', text=prompt)], sandboxPolicy=sandbox, approvalPolicy='on-request')))
            elif message.get('id') == 3 and 'result' in message:
                turn_id = message['result']['turn']['id']
                on_event('WORKING', None)
            elif message.get('method') == 'turn/completed':
                if message['params']['threadId'] != session_id or message['params']['turn']['id'] != turn_id:
                    continue
                status = message['params']['turn']['status']
                return dict(state='FINISHED' if status == 'completed' else 'INTERRUPTED' if status == 'interrupted' else 'FAILED',
                    session_id=session_id, restricted=restricted, failed_tools=failed_tools, tool_calls=tool_calls)
            elif message.get('method') in ('item/started', 'item/completed'):
                item = message.get('params', {}).get('item', {})
                if item.get('type') in ('mcpToolCall', 'fileChange', 'commandExecution'):
                    on_event('ACTION', item.get('type'))
                if message['method'] == 'item/completed' and item.get('type') == 'mcpToolCall':
                    failed_tools |= item.get('status') != 'completed' or bool(item.get('error'))
                    if item.get('server') == 'jiejian' and item.get('tool') in config['jiejian']['enabled_tools'] and len(tool_calls) < 64:
                        tool_calls.append(dict(tool=item['tool'], status=item.get('status')))
            elif 'id' in message and 'method' in message:
                # 任务授权不包含提升沙箱、任意终端或新增网络；这些请求不能自动批准。
                if message['method'] in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
                    send(dict(id=message['id'], result=dict(decision='decline')))
                    on_event('RESTRICTED', None)
                else:
                    send(dict(id=message['id'], error=dict(code=-32601, message='当前执行适配器不支持该交互，请使用界鉴协作工具。')))
                    on_event('RESTRICTED', None)
                restricted = True
        raise JiejianError(ErrorCode.STATE_PRECONDITION, '本轮 Agent 已达到运行时限，请核对原任务后继续')
    finally:
        # Windows Job Object / POSIX 进程组同时覆盖连接器等后代，不遗留后台执行者。
        closed.set()
        terminate_process_tree(process, timeout=5)
        if reader.ident is not None:
            reader.join(timeout=.5)


def _toml_servers(servers):
    item = servers['jiejian']
    # 仅委派本产品的受控命令入口；业务审阅和项目权限继续由服务端执行。
    policies = ','.join(name + '={approval_mode="approve"}' for name in item['tools'])
    return '{jiejian={command=' + json.dumps(item['command']) + ',args=' + json.dumps(item['args']) + \
        ',required=true,default_tools_approval_mode="writes",enabled_tools=' + json.dumps(item['enabled_tools']) + \
        ',tools={' + policies + '}}}'
