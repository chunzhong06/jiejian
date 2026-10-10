# 客户端配置适配：只替换界鉴服务，解析 YAML 不执行标签，拒绝不明格式和冲突条目。
from __future__ import annotations

import base64
import json
import re
import tomllib
from pathlib import Path
from urllib.parse import quote

import yaml

CLIENTS = {'dsh': 'DSH', 'codex': 'Codex', 'zcode': 'ZCode', 'trae': 'TRAE', 'codebuddy': 'CodeBuddy Code', 'qoder': 'Qoder CLI'}


class ConnectionProblem(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def read_config(path: Path) -> str:
    if not path.exists():
        return ''
    if path.is_symlink() or path.resolve() != path.absolute() or path.stat().st_size > 2_000_000:
        raise ConnectionProblem('CONFIG_UNSUPPORTED', '配置使用链接或超过支持的大小，原文件未修改。')
    return path.read_text(encoding='utf-8-sig')


def _json_object(text: str) -> dict:
    try:
        value = json.loads(text or '{}')
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise ConnectionProblem('CONFIG_FORMAT', '客户端配置不是可识别的 JSON 对象，原配置已保留。') from None


def _owned(value: dict, entry: dict) -> None:
    # 名称冲突不能直接覆盖另一项服务；兼容原界鉴回环 HTTP 指引。
    if not value:
        return
    if not isinstance(value, dict):
        raise ConnectionProblem('CONFIG_CONFLICT', '名为 jiejian 的配置格式不明，未覆盖该条目。')
    old_args = value.get('args', [])
    old_url = value.get('url', '')
    if value.get('command') == entry['command'] and old_args == entry['args']:
        return
    if isinstance(old_args, list) and any(isinstance(arg, str) and arg.replace('\\', '/').endswith('/agent_access/connector.py') for arg in old_args):
        return
    if isinstance(old_url, str) and re.fullmatch(r'http://(?:127\.0\.0\.1|localhost):\d+/mcp/?', old_url):
        return
    raise ConnectionProblem('CONFIG_CONFLICT', 'jiejian 名称已被其他配置占用，未覆盖其他服务。')


def json_patch(text: str, entry: dict, *, zcode: bool = False, fallback: str = '') -> str:
    value = _json_object(text)
    if zcode:
        parent = value.setdefault('mcp', {})
        if not isinstance(parent, dict):
            raise ConnectionProblem('CONFIG_FORMAT', 'MCP 配置格式无法识别，原配置已保留。')
        servers = parent.setdefault('servers', {})
        if isinstance(servers, dict) and not servers and fallback:
            inherited = _json_object(fallback).get('mcpServers', {})
            if not isinstance(inherited, dict):
                raise ConnectionProblem('CONFIG_FORMAT', '原 MCP 服务列表格式无法识别，原配置已保留。')
            servers.update(inherited)
    else:
        servers = value.setdefault('mcpServers', {})
    if not isinstance(servers, dict):
        raise ConnectionProblem('CONFIG_FORMAT', 'MCP 服务列表格式无法识别，原配置已保留。')
    _owned(servers.get('jiejian', {}), entry)
    servers['jiejian'] = entry | ({'enable': True} if zcode else {})
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def toml_patch(text: str, entry: dict) -> str:
    try:
        parsed = tomllib.loads(text)
        previous = parsed.get('mcp_servers', {}).get('jiejian', {})
        _owned(previous, entry)
        # 只处理独立表；内联表和带未知子表的配置拒绝猜测，以免改坏其他设置。
        headers = list(re.finditer(r'(?m)^[ \t]*\[([^\r\n]+)\][ \t]*(?:#[^\r\n]*)?$', text))
        own = [i for i, h in enumerate(headers) if h.group(1).replace('"', '').replace("'", '') == 'mcp_servers.jiejian']
        if previous and len(own) != 1:
            raise ValueError()
        replacement = '[mcp_servers.jiejian]\ncommand = '+json.dumps(entry['command'], ensure_ascii=False)+'\nargs = '+json.dumps(entry['args'], ensure_ascii=False)+'\nstartup_timeout_sec = 30\n'
        if own:
            index = own[0]
            end_index = index + 1
            while end_index < len(headers) and headers[end_index].group(1).replace('"', '').replace("'", '').startswith('mcp_servers.jiejian.'):
                end_index += 1
            end = headers[end_index].start() if end_index < len(headers) else len(text)
            text = text[:headers[index].start()] + replacement + ('\n' if end < len(text) else '') + text[end:]
        else:
            text = text.rstrip() + '\n\n' + replacement
        tomllib.loads(text)
        return text
    except (ValueError, TypeError, AttributeError):
        raise ConnectionProblem('CONFIG_FORMAT', 'Codex 配置不是受支持的独立 MCP 表，原文件已保留。') from None


def _field(node, name):
    if isinstance(node, yaml.MappingNode):
        return next((value for key, value in node.value if key.value == name), None)
    return None


def dsh_patch(text: str, entry: dict) -> str:
    try:
        root = yaml.compose(text or '[]', Loader=yaml.SafeLoader)
        if root is None:
            text, root = '', yaml.compose('[]')
        if not isinstance(root, yaml.SequenceNode) or root.flow_style and root.value:
            raise ValueError()
        matches = []
        for row in root.value:
            inserted = _field(row, 'insert')
            nodes = inserted.value if isinstance(inserted, yaml.SequenceNode) else [row]
            found = [node for node in nodes if (_field(node, 'id') is not None and _field(node, 'id').value == 'mcp-jiejian')]
            if found:
                if len(nodes) != 1 or len(found) != 1:
                    raise ConnectionProblem('CONFIG_CONFLICT', 'DSH 的界鉴条目与其他插件共用插入块，不能安全替换该块。')
                matches.append(row)
        if len(matches) > 1:
            raise ConnectionProblem('CONFIG_CONFLICT', 'DSH 有重复的界鉴插件条目，无法确定应启用哪一项。')
        # 用户 patch 中裸 id 只能更新已有插件；必须 insert 才能真正挂载首次添加的插件。
        payload = [{'insert': [{'id': 'mcp-jiejian', 'name': '@deepseek-ai/dsh-mcp-client', 'config': {
            'serverName': 'jiejian', 'transport': 'stdio', **entry, 'failOnStartupError': True}}]}]
        replacement = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
        if matches:
            row = matches[0]
            start = text.rfind('\n', 0, row.start_mark.index) + 1
            end = row.end_mark.index
            text = text[:start] + replacement + text[end:]
        elif not root.value:
            text = replacement
        else:
            text = text.rstrip() + '\n' + replacement
        yaml.compose(text, Loader=yaml.SafeLoader)
        return text
    except (yaml.YAMLError, ValueError, TypeError):
        raise ConnectionProblem('CONFIG_FORMAT', 'DSH patch 无法安全识别，原配置未修改。') from None


def trae_link(entry: dict) -> str:
    config = base64.b64encode(json.dumps(entry, ensure_ascii=False).encode()).decode()
    return 'trae-cn://trae.ai-ide/mcp-import?type=stdio&name=jiejian&config=' + quote(config, safe='')


def connection_matches(client: str, text: str, entry: dict) -> bool:
    """状态只比较自己的连接项，不把其他服务的编辑当作界鉴连接失效。"""
    try:
        if client == 'codex':
            saved = tomllib.loads(text).get('mcp_servers', {}).get('jiejian', {})
        elif client == 'dsh':
            root = yaml.compose(text, Loader=yaml.SafeLoader)
            saved = None
            for row in root.value:
                inserted = _field(row, 'insert')
                for node in inserted.value if isinstance(inserted, yaml.SequenceNode) else [row]:
                    if _field(node, 'id') is not None and _field(node, 'id').value == 'mcp-jiejian':
                        saved = yaml.safe_load(yaml.serialize(_field(node, 'config')))
            if saved is None or saved.get('transport') != 'stdio':
                return False
        else:
            root = _json_object(text)
            saved = root.get('mcp', {}).get('servers', {}).get('jiejian', {}) if client == 'zcode' else root.get('mcpServers', {}).get('jiejian', {})
        return saved.get('command') == entry['command'] and saved.get('args') == entry['args'] and not saved.get('disabled', False) and saved.get('enable', True) is not False
    except (ValueError, TypeError, AttributeError, yaml.YAMLError):
        return False
