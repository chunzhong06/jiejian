# 本机连接安装与回读：客户端配置和真实工具请求分开；配置备份受 DPAPI 保护。
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from threading import RLock
from uuid import uuid4

from product.backend.workflows.agent_access.client_config import (
    CLIENTS, ConnectionProblem, connection_matches, dsh_patch, json_patch, read_config, toml_patch, trae_link,
)
from product.backend.workflows.agent_access.connection_files import (
    ConnectionBackup, ConnectionProfile, ConnectionReceipt, atomic_write, protect, unprotect,
)
from product.backend.workflows.agent_access.connector import MESSAGES


class AgentConnections:
    def __init__(self, root: Path, access, *, home: Path | None = None, environ=None, protector=protect, unprotector=unprotect):
        self.root = Path(root).resolve() / 'runtime' / 'agent-connections'
        self.home = (home or Path.home()).resolve()
        self.environ = os.environ if environ is None else environ
        self.access = access
        self.protect, self.unprotect = protector, unprotector
        self.generations = {client: uuid4().hex for client in CLIENTS}
        self.lock = RLock()
        # 已安装的连接仍指向同一受保护文档；服务重启和端口变化不要求重配客户端。
        for client in CLIENTS:
            if self._profile(client).exists():
                try:
                    self._write_profile(client)
                except Exception:
                    pass  # 状态读取将明确显示受控文档不可用，不影响应用启动。

    def _profile(self, client):
        return self.root / (client + '.bin')

    def _entry(self, client):
        return {'command': str(Path(sys.executable).resolve()), 'args': ['-B', str(Path(__file__).with_name('connector.py').resolve()), '--profile', str(self._profile(client))]}

    def _write_profile(self, client):
        # 每次连接使用独立代次，旧客户端的迟到回执不能把新配置显示成已读取工具。
        generation = uuid4().hex
        value = ConnectionProfile(client=client, endpoint=self.access.view().endpoint, generation=generation)
        atomic_write(self._profile(client), self.protect(value.model_dump_json().encode()))
        self.generations[client] = generation

    def _dsh_root(self):
        return Path(self.environ.get('DSH_HOME') or self.home/'.dsh').resolve()

    def _target(self, client, profile=None):
        if client == 'dsh':
            profiles_root = self._dsh_root()/'profiles'
            profiles = sorted(p.name for p in profiles_root.iterdir() if p.is_dir() and not p.is_symlink())[:30] if profiles_root.is_dir() else []
            selected = profile or ('desktop' if 'desktop' in profiles else profiles[0] if len(profiles) == 1 else None)
            if not profiles:
                raise ConnectionProblem('CLIENT_NOT_FOUND', '没有找到 DSH 配置档。请先安装并打开一次 DSH，再重新检测。')
            if selected not in profiles:
                raise ConnectionProblem('PROFILE_REQUIRED', '请选择实际使用的 DSH 配置档，再建立连接。')
            global_patch = read_config(self._dsh_root()/'cordis.patch.yml')
            if 'mcp-jiejian' in global_patch or 'serverName: jiejian' in global_patch:
                raise ConnectionProblem('CONFIG_CONFLICT', 'DSH 全局配置也声明了界鉴，可能覆盖此配置档；原配置保留，尚未写入。')
            return profiles_root/selected/'cordis.patch.yml'
        if client == 'codex':
            base = Path(self.environ.get('CODEX_HOME') or self.home/'.codex').resolve()
            return base/'config.toml'
        if client == 'zcode':
            return self.home/'.zcode/cli/config.json'
        if client == 'qoder':
            return self.home/'.qoder/settings.json'
        base = self.home/'.codebuddy'
        return base/('.mcp.json' if (base/'.mcp.json').exists() or not (base/'mcp.json').exists() else 'mcp.json')

    def _profiles(self):
        base = self._dsh_root()/'profiles'
        return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.is_symlink())[:30] if base.is_dir() else []

    def _waiting_message(self, client):
        # 安装不会控制外部客户端的重载；提示只描述所选客户端的下一步。
        instructions = {
            'codex': '如果 Codex 尚未加载该配置，请在 Codex 的设置 → MCP 服务器中确认 jiejian 已启用，再点击 Restart（重启）；IDE 扩展需重启扩展，CLI 需重新打开会话。',
            'dsh': '请在 DSH 使用刚才选定的配置档，并确认启用或重载界鉴连接。',
            'trae': '请在 TRAE 的安装确认中添加并启用界鉴连接。',
            'qoder': '请在 Qoder CLI 中执行 /mcp reload，再确认界鉴已启用。',
            'zcode': '请在 ZCode 的 MCP 服务设置中确认界鉴已启用，并重新加载客户端。',
            'codebuddy': '请在 CodeBuddy Code 中确认界鉴 MCP 服务已启用，并重新打开会话。',
        }
        return '配置已保存，尚未收到当前服务的客户端请求。已加载配置的客户端可以直接继续调用，无需重新配置。' + instructions[client]

    def install(self, client, profile=None):
        if client not in CLIENTS:
            raise ValueError('未知客户端')
        with self.lock:
            try:
                entry = self._entry(client)
                if client == 'trae':
                    self.access.pair()
                    self._write_profile(client)
                    return self._view(client, 'AWAITING_CLIENT', '请打开 TRAE 的安装确认，允许添加界鉴连接。', open_url=trae_link(entry))
                target = self._target(client, profile)
                if client != 'dsh' and not target.parent.exists() and not shutil.which({'codex':'codex','qoder':'qoder','zcode':'zcode','codebuddy':'codebuddy'}[client]):
                    raise ConnectionProblem('CLIENT_NOT_FOUND', f'没有找到 {CLIENTS[client]} 的本机配置。请先安装并打开一次客户端，再重新检测。')
                before = read_config(target)
                original = target.read_bytes() if target.exists() else None
                after = dsh_patch(before, entry) if client == 'dsh' else toml_patch(before, entry) if client == 'codex' else json_patch(before, entry,
                    zcode=client == 'zcode', fallback=read_config(self.home/'.agents/mcp.json') if client == 'zcode' else '')
                self.access.pair()  # 凭据只在这里准备，不返回给连接页面或客户端配置。
                self._write_profile(client)
                metadata_path = self.root/(client+'.install.bin')
                if original != (target.read_bytes() if target.exists() else None):
                    raise ConnectionProblem('CONFIG_CHANGED', '客户端同时修改了配置，请重新检测后再连接。')
                # 备份与目标信息一起加密，普通日志/JSON 不保存其他服务可能含有的秘密。
                metadata = ConnectionBackup(target=str(target), before=None if original is None else original.hex(), after_hash=hashlib.sha256(after.encode()).hexdigest())
                if original != after.encode() or not metadata_path.exists():
                    atomic_write(metadata_path, self.protect(metadata.model_dump_json().encode()))
                if original != after.encode():
                    atomic_write(target, after.encode())
                if target.read_bytes() != after.encode():
                    raise ConnectionProblem('CONFIG_CHANGED', '写入后配置又发生变化，请重新检测。')
                return self._view(client, 'AWAITING_CLIENT', self._waiting_message(client), config_path=str(target))
            except ConnectionProblem as exc:
                return self._view(client, 'FAILED', exc.message, code=exc.code, profiles=self._profiles() if client == 'dsh' else [])
            except Exception:
                return self._view(client, 'FAILED', '本机配置或受控存储无法写入。请检查文件占用、只读属性和当前用户权限后重试。', code='LOCAL_WRITE_FAILED')

    def status(self, client):
        with self.lock:
            if not self._profile(client).exists():
                return self._view(client, 'NOT_CONFIGURED', '尚未为此客户端准备连接。')
            try:
                saved = ConnectionProfile.model_validate_json(self.unprotect(self._profile(client).read_bytes()))
                if saved.generation != self.generations[client]:
                    raise ValueError()
                if not self.access.view().accepting_connections:
                    return self._view(client, 'FAILED', '界鉴连接已暂停或凭据已删除，请恢复或重新连接。', code='AUTH_REJECTED')
                if client != 'trae':
                    metadata = ConnectionBackup.model_validate_json(self.unprotect((self.root/(client+'.install.bin')).read_bytes()))
                    if not connection_matches(client, read_config(Path(metadata.target)), self._entry(client)):
                        return self._view(client, 'FAILED', '客户端配置与安装回执不同，尚不能确认配置已生效。请重新连接。', code='CONFIG_CHANGED')
                activity = self._profile(client).with_suffix('.activity.json')
                if activity.exists() and activity.stat().st_size < 4096:
                    receipt = ConnectionReceipt.model_validate_json(activity.read_bytes())
                    if receipt.generation == saved.generation:
                        message = MESSAGES.get(receipt.code, '客户端已启动连接器，正在等待读取工具。')
                        if receipt.state == 'TOOLS_READ':
                            message = f'客户端已读取 {receipt.tool_count} 个界鉴工具。最近活动不代表客户端持续在线。'
                        elif receipt.state == 'REQUEST_ACCEPTED':
                            message = '客户端已通过原连接调用界鉴工具。连接配置可复用；具体操作仍按当前应用授权处理。'
                        elif receipt.state == 'DISCONNECTED':
                            message = '上次连接已经结束，请在客户端重载界鉴连接。'
                        return self._view(client, receipt.state, message, code=receipt.code, tool_count=receipt.tool_count)
                return self._view(client, 'AWAITING_CLIENT', self._waiting_message(client), open_url=trae_link(self._entry(client)) if client == 'trae' else None)
            except Exception:
                return self._view(client, 'FAILED', '连接记录无法读取，请重新建立连接。', code='PROFILE_UNAVAILABLE')

    def restore(self, client):
        with self.lock:
            try:
                metadata_path = self.root/(client+'.install.bin')
                metadata = ConnectionBackup.model_validate_json(self.unprotect(metadata_path.read_bytes()))
                target = Path(metadata.target)
                if hashlib.sha256(target.read_bytes()).hexdigest() != metadata.after_hash:
                    raise ConnectionProblem('CONFIG_CHANGED', '客户端配置后来有过改动，已保留当前文件，没有覆盖恢复。')
                if metadata.before is None:
                    target.unlink()
                else:
                    atomic_write(target, bytes.fromhex(metadata.before))
                metadata_path.unlink()
                self._profile(client).unlink(missing_ok=True)
                return self._view(client, 'NOT_CONFIGURED', '已恢复连接前的配置。其他客户端和项目授权未改变。')
            except ConnectionProblem as exc:
                return self._view(client, 'FAILED', exc.message, code=exc.code)
            except Exception:
                return self._view(client, 'FAILED', '没有可恢复的配置备份，或备份无法读取。', code='RESTORE_UNAVAILABLE')

    def _view(self, client, state, message, **extra):
        return dict(client=client, label=CLIENTS[client], state=state, message=message, code=extra.pop('code', 'NONE'),
                    tool_count=extra.pop('tool_count', 0), profiles=extra.pop('profiles', []), open_url=extra.pop('open_url', None), **extra)
