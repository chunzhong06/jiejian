# stdio 与当前本机 MCP 的透明连接器；stdout 只承载协议，凭据每次从受控存储读取。
from __future__ import annotations

import json
import sys
import time
from queue import Empty, Queue
from threading import Thread
from pathlib import Path

# 源码和便携版均用绝对脚本路径启动，不依赖客户端的 cwd、PATH 或敏感环境变量。
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import httpx
from mcp_types import PROTOCOL_VERSION_META_KEY
from mcp.shared.inbound import NAME_BEARING_METHODS, encode_header_value
from product.backend.infrastructure.secrets import default_secret_store
from product.backend.application.agent_access.service import MCP_PAIRING_SECRET_REF
from product.backend.application.agent_access.connection_files import ConnectionReceipt, atomic_write, read_profile
from product.backend.application.agent_access.dsh_schema import DshToolSchemas, DshSchemaError

MESSAGES = {
    'SERVICE_UNAVAILABLE': '界鉴服务暂不可达或响应中断。恢复运行后可继续使用原连接；本次请求未自动重试，写操作请先核对原回执。',
    'AUTH_REJECTED': '连接已暂停或凭据失效，请回到界鉴恢复连接。',
    'SESSION_EXPIRED': '原会话已失效，下次请求会通过原配置恢复连接。本次请求未自动重试；写操作请先核对原回执。',
    'PROTOCOL_ERROR': '本机服务返回的 MCP 响应无法识别，请查看界鉴连接诊断。',
    'CREDENTIAL_UNAVAILABLE': '无法读取本机受控凭据，请在界鉴重新连接。',
    'EMPTY_TOOLS': '服务返回了空工具列表，尚不能使用界鉴工具，请重新连接。',
    'CONNECT_TIMEOUT': '连接本机界鉴超时。请确认服务已启动；本次业务请求不会自动重放。',
    'RESPONSE_TIMEOUT': '界鉴响应超时。请核对原请求回执后继续，避免重复执行。',
    'PIPE_CLOSED': '客户端已关闭连接器通道，请在客户端重新加载界鉴连接。',
    'CLIENT_SCHEMA_INVALID': '工具定义无法安全适配当前 DSH，尚未交付工具；请更新界鉴并查看连接诊断。',
}


class ResumeRejected(Exception):
    """协议会话重建被拒时跳过尚未发送的业务请求。"""


class IdleInput:
    """有界读取 stdin；空闲返回 None，让主线程串行探测协议而不并发发送请求。"""

    def __init__(self, source, interval=5):
        self.queue = Queue(maxsize=8)
        self.interval = interval
        def read():
            try:
                while True:
                    line = source.readline(4_194_305)
                    self.queue.put(line)
                    if not line or len(line) > 4_194_304:
                        return
            except (OSError, ValueError):
                self.queue.put('')
        # stdin 只能由此线程读取；进程退出时不能等候仍由客户端持有的管道。
        Thread(target=read, daemon=True, name='jiejian-stdin').start()

    def readline(self, _limit):
        try:
            return self.queue.get(timeout=self.interval)
        except Empty:
            return None


def relay(profile, source, destination, secret_store, http, observe, reload_profile=None, diagnose=None):
    """转交当前服务的 JSON 响应和会话；失败的写请求绝不自动重放。"""
    session = None
    version = None
    tools = 0
    failed = False
    initialization = None
    needs_initialize = False
    schemas = DshToolSchemas() if profile.client == 'dsh' else None
    observe('STARTED', 'NONE', 0)
    while True:
        line = source.readline(4_194_305)
        if line == '':
            break
        idle = line is None
        if idle:
            if initialization is None:
                continue
            # ping 只验证当前协议通道，不调用业务工具或重放任何请求。
            line = json.dumps({'jsonrpc':'2.0','id':'jiejian-idle-ping','method':'ping'})
        if len(line) > 4_194_304:
            observe('FAILED', 'PROTOCOL_ERROR', tools)
            return
        try:
            message = json.loads(line)
            if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
                raise ValueError()
        except (ValueError, TypeError):
            observe('FAILED', 'PROTOCOL_ERROR', tools)
            return
        code = None
        if reload_profile is not None:
            try:
                latest = reload_profile()
                if (latest.generation, latest.endpoint) != (profile.generation, profile.endpoint):
                    profile = latest
                    session = None
                    tools = 0
                    needs_initialize = initialization is not None
                    if schemas is not None:
                        schemas.validators.clear()  # 新服务的完整约束必须重新读取，不能沿用旧定义。
                    observe('STARTED', 'NONE', 0)
            except Exception:
                code = 'CREDENTIAL_UNAVAILABLE'
        try:
            token = secret_store.read(MCP_PAIRING_SECRET_REF)
        except Exception:
            token = None
        if not token or code:
            code = 'CREDENTIAL_UNAVAILABLE'
        else:
            method = message.get('method')
            if diagnose:
                diagnose({'server/discover':'NEGOTIATION','initialize':'INITIALIZE','tools/list':'TOOLS_LIST','tools/call':'TOOLS_CALL'}.get(method, 'PROTOCOL'))
            # DSH 自动探测新版协议会订阅长期 SSE。此 stdio 桥只承诺已实现的请求/响应协议，
            # 按 MCP 的方法不存在响应让客户端正常协商旧版，不能广告无法转交的订阅能力。
            if schemas is not None and method == 'server/discover':
                destination.write(json.dumps({'jsonrpc':'2.0','id':message.get('id'),'error':{'code':-32601,'message':'This stdio bridge supports initialize negotiation.'}})+'\n')
                destination.flush()
                continue
            headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json, text/event-stream'}
            if session:
                headers['Mcp-Session-Id'] = session
            if version:
                headers['MCP-Protocol-Version'] = version
            params = message.get('params') or {}
            modern = params.get('_meta', {}).get(PROTOCOL_VERSION_META_KEY) if isinstance(params, dict) else None
            if isinstance(modern, str):
                headers['MCP-Protocol-Version'] = modern
                headers['Mcp-Method'] = message.get('method', '')
                name = params.get(NAME_BEARING_METHODS.get(message.get('method')))
                if isinstance(name, str):
                    headers['Mcp-Name'] = encode_header_value(name)
            try:
                # 服务重启后只重建协议会话，业务请求尚未发送；绝不重放失败的工具调用。
                if needs_initialize and message.get('method') != 'initialize':
                    resume = http.post(profile.endpoint, json={'jsonrpc':'2.0','id':'jiejian-resume','method':'initialize','params':initialization}, headers=headers, **({'timeout':5} if idle else {}))
                    if resume.status_code in (401, 403):
                        code = 'AUTH_REJECTED'
                    elif resume.status_code >= 300:
                        code = 'PROTOCOL_ERROR'
                    else:
                        result = resume.json().get('result', {})
                        if not result.get('protocolVersion'):
                            raise ValueError()
                        session = resume.headers.get('Mcp-Session-Id')
                        version = result['protocolVersion']
                        if session:
                            headers['Mcp-Session-Id'] = session
                        headers['MCP-Protocol-Version'] = version
                        ready = http.post(profile.endpoint, json={'jsonrpc':'2.0','method':'notifications/initialized'}, headers=headers, **({'timeout':5} if idle else {}))
                        if ready.status_code >= 300:
                            code = 'AUTH_REJECTED' if ready.status_code in (401,403) else 'PROTOCOL_ERROR'
                        else:
                            needs_initialize = False
                if code:
                    raise ResumeRejected()
                if schemas is not None and method == 'tools/call':
                    if not schemas.validators:
                        discovery = http.post(profile.endpoint, json={'jsonrpc':'2.0','id':'jiejian-schema','method':'tools/list'}, headers=headers)
                        if discovery.status_code in (401,403):
                            code = 'AUTH_REJECTED'
                            raise ResumeRejected()
                        schemas.adapt(discovery.json())
                    issues = schemas.validation_issues(params.get('name'), params.get('arguments', {}))
                    if issues:
                        summary = '；'.join(f"{item['path']}：{item['message']}" for item in issues[:3])
                        destination.write(json.dumps({'jsonrpc':'2.0','id':message.get('id'),'error':{'code':-32602,'message':'工具参数不符合原始完整定义：'+summary,'data':{'issues':issues}}},ensure_ascii=False)+'\n')
                        destination.flush()
                        continue
                response = http.post(profile.endpoint, json=message, headers=headers, **({'timeout':5} if idle else {}))
                if response.status_code in (401, 403):
                    code = 'AUTH_REJECTED'
                elif response.status_code == 404 and session:
                    code = 'SESSION_EXPIRED'
                    session = None
                    needs_initialize = initialization is not None
                elif 'id' in message:
                    payload = response.json()
                    if not isinstance(payload, dict) or payload.get('id') != message['id'] or payload.get('jsonrpc') != '2.0':
                        raise ValueError()
                    session = response.headers.get('Mcp-Session-Id', session)
                    if message.get('method') == 'initialize' and 'result' in payload:
                        version = payload['result'].get('protocolVersion')
                        initialization = params
                        needs_initialize = False
                    if schemas is not None and method == 'tools/list' and 'tools' in payload.get('result', {}):
                        payload = schemas.adapt(payload)
                    if not idle:
                        destination.write(json.dumps(payload, ensure_ascii=False) + '\n')
                        destination.flush()
                    elif response.status_code >= 300 or 'error' in payload or not isinstance(payload.get('result'), dict):
                        raise ValueError()
                    else:
                        # 新代次的 ping 成功只能确认连接，不能补造客户端已读工具的回执。
                        observe('TOOLS_READ' if tools else 'CONNECTED', 'NONE', tools)
                        failed = False
                    if message.get('method') == 'tools/list' and isinstance(payload.get('result', {}).get('tools'), list):
                        tools = len(payload['result']['tools'])
                        observe('TOOLS_READ' if tools else 'FAILED', 'NONE' if tools else 'EMPTY_TOOLS', tools)
                        failed = not bool(tools)
                    elif message.get('method') == 'tools/call' and 'result' in payload:
                        observe('REQUEST_ACCEPTED', 'NONE', tools)
                        failed = False
                elif response.status_code >= 300:
                    code = 'PROTOCOL_ERROR'
                elif method == 'notifications/initialized':
                    observe('CONNECTED', 'NONE', tools)
                    failed = False
            except ResumeRejected:
                pass
            except httpx.ConnectTimeout:
                code = 'CONNECT_TIMEOUT'
            except httpx.TimeoutException:
                code = 'RESPONSE_TIMEOUT'
            except httpx.RequestError:
                code = 'SERVICE_UNAVAILABLE'
            except (BrokenPipeError, OSError):
                observe('FAILED', 'PIPE_CLOSED', tools)
                return
            except DshSchemaError:
                code = 'CLIENT_SCHEMA_INVALID'
            except (ValueError, TypeError, KeyError):
                code = 'PROTOCOL_ERROR'
        if code:
            failed = True
            observe('FAILED', code, tools)
            if 'id' in message and not idle:
                destination.write(json.dumps({'jsonrpc':'2.0','id':message['id'],'error':{'code':-32000,'message':MESSAGES[code]}}, ensure_ascii=False)+'\n')
                destination.flush()
            # 客户端保持打开即可在服务恢复后发起下一次请求；暂停/撤权仍由原服务拒绝。
            continue
    if not failed:
        observe('DISCONNECTED', 'NONE', tools)


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != '--profile':
        return 2
    profile_path = Path(sys.argv[2]).resolve()
    try:
        profile = read_profile(profile_path)
        phase = 'STARTUP'
        phase_started = time.monotonic()
        def diagnose(value):
            nonlocal phase, phase_started
            phase, phase_started = value, time.monotonic()
            if value in ('NEGOTIATION', 'INITIALIZE', 'TOOLS_LIST'):
                observe('STARTED', 'NONE', 0)
        def reload_profile():
            nonlocal profile
            profile = read_profile(profile_path)
            return profile
        def observe(state, code, count):
            receipt = ConnectionReceipt(generation=profile.generation, state=state, code=code, tool_count=count, at_us=time.time_ns()//1000,
                                        phase=phase, elapsed_ms=max(0,round((time.monotonic()-phase_started)*1000)))
            atomic_write(profile_path.with_suffix('.activity.json'), receipt.model_dump_json().encode())
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8', newline='\n')
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(65, connect=5)) as http:
            relay(profile, IdleInput(sys.stdin), sys.stdout, default_secret_store(), http, observe, reload_profile, diagnose)
        return 0
    except Exception:
        # 不打印异常对象：第三方异常可能携带请求头、配置或协议正文。
        sys.stderr.write('界鉴连接器无法启动，请回到界鉴重新连接。\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
