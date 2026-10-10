# stdio 与当前本机 MCP 的透明连接器；stdout 只承载协议，凭据每次从受控存储读取。
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# 源码和便携版均用绝对脚本路径启动，不依赖客户端的 cwd、PATH 或敏感环境变量。
if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import httpx
from mcp_types import PROTOCOL_VERSION_META_KEY
from mcp.shared.inbound import NAME_BEARING_METHODS, encode_header_value
from product.backend.infra.secrets import default_secret_store
from product.backend.workflows.agent_access.service import MCP_PAIRING_SECRET_REF
from product.backend.workflows.agent_access.connection_files import ConnectionReceipt, atomic_write, read_profile

MESSAGES = {
    'SERVICE_UNAVAILABLE': '界鉴服务暂不可达或响应中断。恢复运行后可继续使用原连接；本次请求未自动重试，写操作请先核对原回执。',
    'AUTH_REJECTED': '连接已暂停或凭据失效，请回到界鉴恢复连接。',
    'SESSION_EXPIRED': '界鉴服务已重新启动，请在客户端重新加载界鉴连接。',
    'PROTOCOL_ERROR': '本机服务返回的 MCP 响应无法识别，请查看界鉴连接诊断。',
    'CREDENTIAL_UNAVAILABLE': '无法读取本机受控凭据，请在界鉴重新连接。',
    'EMPTY_TOOLS': '服务返回了空工具列表，尚不能使用界鉴工具，请重新连接。',
}


class ResumeRejected(Exception):
    """协议会话重建被拒时跳过尚未发送的业务请求。"""


def relay(profile, source, destination, secret_store, http, observe, reload_profile=None):
    """转交当前服务的 JSON 响应和会话；失败的写请求绝不自动重放。"""
    session = None
    version = None
    tools = 0
    failed = False
    initialization = None
    needs_initialize = False
    observe('STARTED', 'NONE', 0)
    while line := source.readline(4_194_305):
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
                    needs_initialize = initialization is not None
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
                    resume = http.post(profile.endpoint, json={'jsonrpc':'2.0','id':'jiejian-resume','method':'initialize','params':initialization}, headers=headers)
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
                        ready = http.post(profile.endpoint, json={'jsonrpc':'2.0','method':'notifications/initialized'}, headers=headers)
                        if ready.status_code >= 300:
                            code = 'AUTH_REJECTED' if ready.status_code in (401,403) else 'PROTOCOL_ERROR'
                        else:
                            needs_initialize = False
                if code:
                    raise ResumeRejected()
                response = http.post(profile.endpoint, json=message, headers=headers)
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
                    destination.write(json.dumps(payload, ensure_ascii=False) + '\n')
                    destination.flush()
                    if message.get('method') == 'tools/list' and isinstance(payload.get('result', {}).get('tools'), list):
                        tools = len(payload['result']['tools'])
                        observe('TOOLS_READ' if tools else 'FAILED', 'NONE' if tools else 'EMPTY_TOOLS', tools)
                        failed = not bool(tools)
                    elif message.get('method') == 'tools/call' and 'result' in payload:
                        observe('REQUEST_ACCEPTED', 'NONE', tools)
                        failed = False
                elif response.status_code >= 300:
                    code = 'PROTOCOL_ERROR'
            except ResumeRejected:
                pass
            except (httpx.RequestError, OSError):
                code = 'SERVICE_UNAVAILABLE'
            except (ValueError, TypeError, KeyError):
                code = 'PROTOCOL_ERROR'
        if code:
            failed = True
            observe('FAILED', code, tools)
            if 'id' in message:
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
        def reload_profile():
            nonlocal profile
            profile = read_profile(profile_path)
            return profile
        def observe(state, code, count):
            receipt = ConnectionReceipt(generation=profile.generation, state=state, code=code, tool_count=count, at_us=time.time_ns()//1000)
            atomic_write(profile_path.with_suffix('.activity.json'), receipt.model_dump_json().encode())
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8', newline='\n')
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(65, connect=5)) as http:
            relay(profile, sys.stdin, sys.stdout, default_secret_store(), http, observe, reload_profile)
        return 0
    except Exception:
        # 不打印异常对象：第三方异常可能携带请求头、配置或协议正文。
        sys.stderr.write('界鉴连接器无法启动，请回到界鉴重新连接。\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
