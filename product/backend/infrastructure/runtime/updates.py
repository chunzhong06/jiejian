from __future__ import annotations

import argparse
import configparser
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from product.backend import __version__
from product.backend.domain.errors import ErrorCode, JiejianError
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.runtime.process.lock import lock_is_available
from product.backend.infrastructure.maintenance.inventory import exclusive_file
from product.backend.infrastructure.storage.schema import sqlite_schema_signature
from product.backend.infrastructure.storage.workspace import WORKSPACE_FORMAT
from product.protocols.codec import decode_json, encode_json
from product.protocols.runtime.portable_release import PortableReleaseManifest
from product.protocols.runtime.portable_update import PortableExitReceipt, PortableUpdateManifest, PortableUpdateOperation


def file_digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_root(path: Path, model):
    with path.open('rb') as stream:
        raw = stream.read(8 * 1024 * 1024 + 1)
    payload = decode_json(raw, limit=8 * 1024 * 1024)
    if 'schema_version' not in payload:
        raise ValueError('missing root format')
    return model.model_validate(payload)


def package_files(root: Path) -> list[Path]:
    files = [root / '界鉴.exe']
    for name in ('app', 'runtime'):
        if (root / name).is_symlink() or (root / name).is_junction():
            raise ValueError('linked release tree')
        for directory, subdirs, names in os.walk(root / name, followlinks=False):
            for child in [Path(directory) / value for value in (*subdirs, *names)]:
                if child.is_symlink() or child.is_junction():
                    raise ValueError('linked release file')
            files.extend(Path(directory) / value for value in names if Path(directory) / value != root / 'app/update-manifest.json')
            if len(files) > 30000:
                raise ValueError('release file limit')
    return files


def verify_package(root: Path, workspace: Path) -> tuple[PortableUpdateManifest, str, bool]:
    # 交接只接纳新发行，不能覆盖另一个实例的数据或工作区绑定。
    if any(path.is_symlink() or path.is_junction() for path in (root/'var', root/'var/launcher')):
        raise ValueError('linked target workspace')
    if RuntimePaths(root / 'var').database.exists():
        raise ValueError('target already owns business data')
    binding = root / 'var/launcher/workspace.ini'
    if binding.exists():
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(binding.read_text('utf-16'))
        if Path(config['workspace']['path']).resolve() != workspace.resolve():
            raise ValueError('target bound to another workspace')
    manifest_path = root / 'app' / 'update-manifest.json'
    manifest = read_root(manifest_path, PortableUpdateManifest)
    release = read_root(root / 'app' / 'release.json', PortableReleaseManifest)
    names = [item.relative_path for item in manifest.files]
    required = {'界鉴.exe', 'app/start.ps1', 'app/release.json', 'runtime/python/python.exe', 'runtime/node/node.exe',
                'app/product/frontend/dist/index.html', 'app/product/backend/__init__.py',
                'runtime/python/Lib/site-packages/jiejian-app.pth'}
    if (manifest.version != release.version or not required.issubset(names) or len({name.casefold() for name in names}) != len(names)
            or not any(name.startswith('runtime/playwright/chromium-') and name.endswith('/chrome.exe') for name in names)):
        raise ValueError('incomplete release')
    # 清单必须覆盖实际可执行树，未登记模块同样会影响新程序的运行身份。
    if {path.relative_to(root).as_posix() for path in package_files(root)} != set(names):
        raise ValueError('unlisted release file')
    for item in manifest.files:
        path = (root / item.relative_path).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_digest(path) != item.sha256:
            raise ValueError('release files changed')
    database = RuntimePaths(workspace).database
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as connection:
        # 活跃服务可继续提交；身份、结构和外键必须来自同一个只读快照。
        connection.execute('BEGIN')
        identity = connection.execute('SELECT singleton, format, generation, schema_digest FROM workspace_schema').fetchall()
        revision = connection.execute('SELECT version_num FROM alembic_version').fetchall()
        if len(identity) != 1 or len(revision) != 1:
            raise ValueError('workspace unsupported')
        singleton, format_name, generation, digest = identity[0]
        accepted = {(item.generation, item.revision, item.schema_digest) for item in manifest.supported_workspaces}
        actual = hashlib.sha256(json.dumps(sqlite_schema_signature(connection), ensure_ascii=False,
            separators=(',', ':')).encode()).hexdigest()
        if (singleton != 1 or format_name != WORKSPACE_FORMAT or (generation, revision[0][0], digest) not in accepted
                or actual != digest or connection.execute('PRAGMA foreign_key_check').fetchone() is not None):
            raise ValueError('workspace unsupported')
    return manifest, file_digest(manifest_path), revision[0][0] != manifest.workspace_revision


class PortableUpdateService:
    """只准备本机发行交接；HTTP 不启动程序，实际接续由退出后的启动器承担。"""

    def __init__(self, var_dir: Path, environment: dict[str, str]):
        self.paths = RuntimePaths(var_dir)
        self.environment = environment
        self.records = self.paths.runtime / 'updates'

    def info(self) -> dict:
        release = self.environment.get('JIEJIAN_RELEASE_ROOT')
        return {'version': __version__, 'portable': self.environment.get('JIEJIAN_RUNTIME_MODE') == 'portable',
                'release_root': release, 'workspace': str(self.paths.root), 'operation': self.latest(), 'last_exit': self.last_exit()}

    def last_exit(self) -> dict | None:
        path = self.paths.runtime / 'last-exit.json'
        return read_root(path, PortableExitReceipt).model_dump(mode='json') if path.is_file() else None

    def latest(self) -> dict | None:
        pointer = self.records / 'current.json'
        if not pointer.is_file():
            return None
        operation = read_root(pointer, PortableUpdateOperation)
        return self.read(operation.operation_id).model_dump(mode='json')

    def read(self, operation_id: str) -> PortableUpdateOperation:
        if not re.fullmatch(r'upd_[0-9a-f]{32}', operation_id):
            raise JiejianError(ErrorCode.INPUT_INVALID, '更新操作标识无效')
        try:
            return read_root(self.records / (operation_id + '.json'), PortableUpdateOperation)
        except FileNotFoundError:
            raise JiejianError(ErrorCode.INPUT_INVALID, '未找到该更新，请返回版本与更新查看当前操作') from None

    def _save(self, operation: PortableUpdateOperation) -> None:
        self.records.mkdir(parents=True, exist_ok=True)
        data = encode_json(operation.model_dump(mode='json'))
        for path in (self.records / (operation.operation_id + '.json'), self.records / 'current.json'):
            temporary = path.with_suffix('.tmp')
            with temporary.open('wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)

    def preview(self, directory: str, return_path: str = '/workspace') -> dict:
        if not self.info()['portable']:
            raise JiejianError(ErrorCode.INPUT_INVALID, '源码运行不执行发行更新，请从便携版打开此功能')
        root = Path(directory).expanduser().resolve()
        previous = Path(self.environment['JIEJIAN_RELEASE_ROOT']).resolve()
        if root == previous or root.is_relative_to(self.paths.root) or self.paths.root.is_relative_to(root):
            raise JiejianError(ErrorCode.INPUT_INVALID, '请选择与当前程序及工作区独立的新发行目录')
        try:
            manifest, digest, workspace_upgrade = verify_package(root, self.paths.root)
        except (OSError, ValueError, KeyError, configparser.Error, sqlite3.Error) as error:
            occupied = str(error) in {'target already owns business data', 'target bound to another workspace', 'linked target workspace'}
            message = '目标目录已有工作区或外部绑定，请选择新解压的发行目录；原工作区未修改' if occupied else '发行文件不完整、已变化或不支持当前工作区；原工作区未修改'
            raise JiejianError(ErrorCode.INPUT_INVALID, message) from None
        origin = urlsplit(self.environment.get('JIEJIAN_CONTROL_ORIGIN', 'http://127.0.0.1:8765'))
        operation = PortableUpdateOperation(schema_version='1', document_type='jiejian.portable-update-operation',
            operation_id='upd_' + uuid4().hex, workspace=str(self.paths.root), previous_release=str(previous),
            target_release=str(root), manifest_digest=digest, target_version=manifest.version,
            port=origin.port or 8765, created_at=time.time(), phase='PREVIEWED', workspace_upgrade=workspace_upgrade,
            return_path=return_path if re.fullmatch(r'/workspace(?:\?project_id=app_[0-9a-f]{32})?', return_path) else '/workspace')
        self.records.mkdir(parents=True, exist_ok=True)
        with exclusive_file(self.records / 'update.lock'):
            latest = self.latest()
            if latest and latest['phase'] in {'WAITING_FOR_EXIT', 'STARTING'}:
                raise JiejianError(ErrorCode.INPUT_INVALID, '已有更新正在交接，请查询原操作')
            self._save(operation)
        return operation.model_dump(mode='json')

    def confirm(self, operation_id: str) -> dict:
        self.records.mkdir(parents=True, exist_ok=True)
        with exclusive_file(self.records / 'update.lock'):
            return self._confirm(operation_id)

    def _confirm(self, operation_id: str) -> dict:
        operation = self.read(operation_id)
        latest = self.latest()
        if latest and latest['operation_id'] != operation_id and latest['phase'] in {'WAITING_FOR_EXIT', 'STARTING'}:
            raise JiejianError(ErrorCode.INPUT_INVALID, '已有更新正在交接，请查询原操作')
        if Path(operation.workspace) != self.paths.root or operation.previous_release != self.environment.get('JIEJIAN_RELEASE_ROOT'):
            raise JiejianError(ErrorCode.INPUT_INVALID, '该更新不属于当前运行实例')
        if operation.phase != 'PREVIEWED':
            return operation.model_dump(mode='json')
        if time.time() - operation.created_at > 600:
            raise JiejianError(ErrorCode.INPUT_INVALID, '更新预览已过期或目标改变，请重新核对')
        # 确认已跨过用户选择窗口；先核对实际文件，避免停止服务后才发现目标被替换。
        try:
            _, digest, _ = verify_package(Path(operation.target_release), self.paths.root)
        except (OSError, ValueError, KeyError, configparser.Error, sqlite3.Error):
            raise JiejianError(ErrorCode.INPUT_INVALID, '目标文件或工作区已变化，请重新核对；当前服务未停止') from None
        if digest != operation.manifest_digest:
            raise JiejianError(ErrorCode.INPUT_INVALID, '更新预览已过期或目标改变，请重新核对')
        operation = operation.model_copy(update={'phase': 'WAITING_FOR_EXIT'})
        self._save(operation)
        return operation.model_dump(mode='json')

    def ready(self) -> None:
        latest = self.latest()
        if not latest:
            return
        operation = PortableUpdateOperation.model_validate(latest)
        release = self.environment.get('JIEJIAN_RELEASE_ROOT')
        if operation.phase == 'STARTING' and release and Path(release).resolve() == Path(operation.target_release):
            self._save(operation.model_copy(update={'phase': 'READY'}))

    def accept_startup(self) -> None:
        """仅由已取得工作区服务锁的入口调用，显式返回原程序使未完成交接收口。"""
        if not self.environment.get('JIEJIAN_RELEASE_ROOT'):
            return
        self.records.mkdir(parents=True, exist_ok=True)
        with exclusive_file(self.records / 'update.lock'):
            latest = self.latest()
            if latest and latest['phase'] in {'WAITING_FOR_EXIT', 'STARTING'}:
                operation = PortableUpdateOperation.model_validate(latest)
                if Path(self.environment['JIEJIAN_RELEASE_ROOT']).resolve() != Path(operation.target_release):
                    self._save(operation.model_copy(update={'phase': 'FAILED', 'reason': '交接未完成，当前已由原程序重新打开；工作区保留'}))


def finish_after_exit(var_dir: Path, release_root: Path, exit_code: int = 0) -> None:
    service = PortableUpdateService(var_dir, {'JIEJIAN_RELEASE_ROOT': str(release_root), 'JIEJIAN_RUNTIME_MODE': 'portable'})
    stopped = lock_is_available(RuntimePaths(var_dir).locks / 'serve.lock')
    exit_receipt = RuntimePaths(var_dir).runtime / 'last-exit.json'
    exit_receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary = exit_receipt.with_suffix('.tmp')
    receipt = PortableExitReceipt(schema_version='1', document_type='jiejian.portable-exit',
        state='STOPPED' if stopped and exit_code == 0 else 'NEEDS_REVIEW', finished_at=time.time(), exit_code=exit_code)
    with temporary.open('wb') as stream:
        stream.write(encode_json(receipt.model_dump(mode='json')))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, exit_receipt)
    service.records.mkdir(parents=True, exist_ok=True)
    with exclusive_file(service.records / 'update.lock'):
        _finish_update(service, release_root, exit_code, stopped)


def _finish_update(service: PortableUpdateService, release_root: Path, exit_code: int, stopped: bool) -> None:
    var_dir = service.paths.root
    latest = service.latest()
    if latest and latest['phase'] == 'STARTING' and Path(latest['target_release']) == release_root.resolve():
        operation = PortableUpdateOperation.model_validate(latest)
        service._save(operation.model_copy(update={'phase': 'FAILED', 'reason': '新版本在就绪前停止，工作区数据保留'}))
        return
    if not latest or latest['phase'] != 'WAITING_FOR_EXIT' or Path(latest['previous_release']) != release_root.resolve():
        return
    operation = PortableUpdateOperation.model_validate(latest)
    try:
        if not stopped or exit_code != 0:
            raise ValueError('workspace still running')
        root = Path(operation.target_release)
        _, digest, _ = verify_package(root, var_dir)
        if digest != operation.manifest_digest:
            raise ValueError('target replaced')
        # 新程序绑定原工作区，数据和绝对引用不移动；绑定是启动配置，不是业务资料副本。
        binding = root / 'var' / 'launcher' / 'workspace.ini'
        binding.parent.mkdir(parents=True, exist_ok=True)
        config = configparser.ConfigParser(interpolation=None)
        config['workspace'] = {'version': '1', 'path': str(var_dir.resolve())}
        binding_temp = binding.with_suffix('.tmp')
        with binding_temp.open('w', encoding='utf-16') as stream:
            config.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(binding_temp, binding)
        service._save(operation.model_copy(update={'phase': 'STARTING'}))
        subprocess.Popen([str(root / '界鉴.exe'), '--workspace', str(var_dir.resolve()), '--port', str(operation.port)],
                         cwd=root, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
    except (OSError, ValueError, KeyError, configparser.Error, sqlite3.Error):
        service._save(operation.model_copy(update={'phase': 'FAILED', 'reason': '新版本未能启动，数据保留，请核对目标程序及运行诊断'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--var-dir', type=Path, required=True)
    parser.add_argument('--release-root', type=Path, required=True)
    parser.add_argument('--exit-code', type=int, default=0)
    arguments = parser.parse_args()
    finish_after_exit(arguments.var_dir, arguments.release_root, arguments.exit_code)
