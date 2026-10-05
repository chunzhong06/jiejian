# 启动和运行生成物的归属、引用与安全枚举；开发审阅目录和业务资料不进入删除候选。
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.process.lock import try_lock_stream, unlock_stream, lock_is_available


def linked(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except OSError:
        return True


def safe_tree(path: Path, root: Path) -> bool:
    """拒绝任何祖先或后代链接，不能通过目录联接把排除目录带进清理。"""
    path, root = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    if path == root or not path.is_relative_to(root):
        return False
    for parent in (path, *path.parents):
        if linked(parent):
            return False
    try:
        if path.is_file():
            return True
        def failed(error):
            raise error
        for folder, dirs, files in os.walk(path, followlinks=False, onerror=failed):
            if any(linked(Path(folder) / name) for name in (*dirs, *files)):
                return False
        return True
    except OSError:
        return False


def read_record(path: Path) -> dict | None:
    try:
        if linked(path) or path.stat().st_size > 1024 * 1024:
            return None
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value, dict) and value.get('schema_version') == '1' else None
    except (OSError, ValueError):
        return None


def children(path: Path) -> list[Path]:
    try:
        return list(path.iterdir()) if path.is_dir() and not linked(path) else []
    except OSError:
        return []


def overlaps(path: Path, protected) -> bool:
    return any(path == other or path.is_relative_to(other) or other.is_relative_to(path) for other in protected)


def component_in_use(path: Path) -> bool:
    """Windows 映射中的程序不能取得独占写句柄；只探测句柄，不写入或终止进程。"""
    if os.name != 'nt':
        return True
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    images=[path] if path.is_file() else [item for item in path.rglob('*') if item.suffix.lower() in {'.exe','.dll','.pyd'}]
    for image in images:
        handle=kernel.CreateFileW(str(image),0xC0000000,0,None,3,0,None)
        if handle==ctypes.c_void_p(-1).value:
            return True
        kernel.CloseHandle(handle)
    return False


@contextmanager
def exclusive_file(path: Path):
    """兼容启动脚本的 FileShare.None；锁定期间禁止准备过程切换共享引用。"""
    stream = None
    acquired = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stream = path.open('a+b')
        acquired = try_lock_stream(stream)
        if not acquired:
            raise OSError('busy')
    except OSError:
        if stream:
            stream.close()
        raise JiejianError(ErrorCode.LOCAL_MAINTENANCE_FAILED, '运行环境正在准备或清理，请稍后重新扫描', details={'execution_started':False}) from None
    try:
        yield
    finally:
        if acquired:
            unlock_stream(stream)
        stream.close()


@dataclass(frozen=True)
class Asset:
    path: Path
    root: Path
    category: str
    label: str
    state: str
    reason: str


def source_references(var_dir: Path) -> tuple[Path, ...] | None:
    source = read_record(var_dir / 'runtime/source/receipt.json')
    build = read_record(var_dir / 'runtime/build/frontend-receipt.json')
    if not source or not build or source.get('runtime_mode') != 'development':
        return None
    values = [build.get('shared_build'), build.get('dist')]
    for key in ('python', 'uv', 'node', 'pnpm', 'playwright'):
        part = source.get(key)
        if not isinstance(part, dict):
            return None
        values.append(part.get('executable'))
    if any(not isinstance(value, str) or not value or not Path(value).is_absolute() for value in values):
        return None
    return tuple(Path(value).resolve() for value in values)


class StartupAssets:
    """只管理启动器确认的共享根；运行回执是引用来源，目录名称不是删除授权。"""
    def __init__(self, var_dir: Path, development_root: Path | None = None):
        self.var_dir = var_dir.resolve()
        source = read_record(self.var_dir / 'runtime/source/receipt.json')
        if development_root is None and source and source.get('runtime_mode') == 'development':
            project = source.get('project_root')
            if (isinstance(project, str) and Path(project).is_absolute()
                    and (Path(project) / 'product/backend/infra/runtime/maintenance_assets.py').resolve() == Path(__file__).resolve()
                    and source.get('var_dir') == str(self.var_dir)):
                development_root = Path(project) / 'var/development'
        self.root = development_root.resolve() if development_root else None
        self._live = None
        self._live_file = None

    @contextmanager
    def locked(self):
        if self.root is None:
            yield
        else:
            with exclusive_file(self.root / 'locks/prepare.lock'):
                yield

    def retain_live_references(self) -> None:
        """固定当前进程实际使用的版本，后续 prepare 更新同一实例回执也不会丢失旧引用。"""
        references = source_references(self.var_dir)
        if self.root is None or references is None:
            return
        with self.locked():
            # 一并固定浏览器的无头/编码组件，避免下次升级覆盖 pin 后仍存活的旧实例失去保护。
            pinned, _ = self.references()
            references = tuple(set(references) | pinned)
            directory = self.root / 'state/runtime-uses'
            directory.mkdir(parents=True, exist_ok=True)
            self._live_file = directory / f'{uuid4().hex}.json'
            lock = self._live_file.with_suffix('.lock')
            self._live = lock.open('a+b')
            if not try_lock_stream(self._live):
                self._live.close(); self._live = None
                raise JiejianError(ErrorCode.LOCAL_MAINTENANCE_FAILED, '无法登记当前运行环境的使用状态')
            self._live_file.write_text(json.dumps({'schema_version':'1', 'kind':'runtime-use', 'paths':[str(p) for p in references]}), encoding='utf-8')

    def close(self) -> None:
        if self._live:
            unlock_stream(self._live); self._live.close(); self._live = None
        # 关闭只释放生存期锁；遗留收据由扫描忽略，避免与另一清理进程争抢共享锁。

    def references(self) -> tuple[set[Path], bool]:
        references = source_references(self.var_dir)
        protected = set(references or ())
        valid = references is not None
        if self.root is None:
            return protected, False
        for pin in children(self.root / 'state/startup-instances'):
            record = read_record(pin)
            if not record or record.get('kind') != 'startup-instance' or not isinstance(record.get('var_dir'), str):
                valid = False; continue
            other = Path(record['var_dir'])
            if not other.is_absolute():
                valid = False; continue
            refs = source_references(other)
            if refs is None:
                valid = False
            else:
                protected.update(refs)
                pinned = record.get('paths', [])
                if not isinstance(pinned,list) or not all(isinstance(p,str) and Path(p).is_absolute() for p in pinned):
                    valid = False
                else:
                    protected.update(Path(p).resolve() for p in pinned)
        for pin in children(self.root / 'state/runtime-uses'):
            if pin.suffix != '.json':
                continue
            lock = pin.with_suffix('.lock')
            try:
                in_use = lock.exists() and not lock_is_available(lock)
            except OSError:
                in_use = True
            if not in_use:
                continue
            record = read_record(pin)
            values = record.get('paths') if record else None
            if not record or record.get('kind') != 'runtime-use' or not isinstance(values, list) or not all(isinstance(p,str) and Path(p).is_absolute() for p in values):
                valid = False
            else:
                protected.update(Path(p).resolve() for p in values)
        # 当前依赖工作区供正常启动与编辑器使用；不因运行时暂未构建而删除。
        protected.add(self.root / 'frontend/workspace')
        return protected, valid

    def scan(self) -> list[Asset]:
        if self.root is None:
            return []
        protected, references_valid = self.references()
        result = []
        def add(path, category, label, known):
            state, reason = 'CLEANABLE', '启动产生且当前没有引用'
            if not known:
                state, reason = 'UNKNOWN', '缺少启动生成记录，暂不处理'
            elif not references_valid:
                state, reason = 'UNKNOWN', '实例运行回执不完整，无法排除仍有引用'
            elif overlaps(path.resolve(), protected):
                state, reason = 'PROTECTED', '当前实例或其他已登记实例仍需使用'
            elif not safe_tree(path, self.root):
                state, reason = 'UNKNOWN', '包含链接或无法完整读取，暂不处理'
            elif category == 'components' and component_in_use(path):
                state, reason = 'PROTECTED', '组件仍被进程使用或无法确认可独占访问'
            result.append(Asset(path, self.root, category, label, state, reason))
        for path in children(self.root / 'frontend/builds'):
            receipt = read_record(path / 'receipt.json')
            add(path, 'builds', '前端构建', bool(receipt and receipt.get('build_digest') == path.name and (path / 'dist/index.html').is_file()))
        for name in ('uv','pnpm-store','vite','downloads'):
            path = self.root / 'cache' / name
            if path.exists():
                marker = read_record(path / '.startup-owned.json')
                add(path, 'build_cache', '下载与构建缓存', bool(marker and marker.get('kind') == 'startup-cache' and marker.get('name') == name))
        for tool in children(self.root / 'tools'):
            for version in children(tool):
                if version.name.startswith('.'):
                    continue
                marker = read_record(version / '.startup-owned.json')
                add(version, 'components', '运行组件', bool(marker and marker.get('kind') == 'startup-component' and marker.get('name') == version.name))
        for path in children(self.root / 'temp'):
            marker = read_record(path / '.startup-owned.json') if path.is_dir() else None
            add(path, 'build_cache', '启动临时文件', bool(marker and marker.get('kind') == 'startup-temporary'))
        return result


def mark_runtime_idle(var_dir: Path, path: Path, producer: str) -> None:
    """仅由已完成退出和凭据回收的生产者调用；失去该证明的目录保持未知。"""
    root = var_dir.resolve()
    allowed = {'identity-preparation': root / 'runtime/identity-preparations'}
    if producer not in allowed or path.parent.resolve() != allowed[producer] or not safe_tree(path, root):
        return
    record = {'schema_version':'1','kind':'runtime-idle','producer':producer,'name':path.name}
    temporary = path / '.runtime-idle.tmp'
    temporary.write_text(json.dumps(record), encoding='utf-8')
    os.replace(temporary, path / '.runtime-idle.json')


def register_startup_assets(var_dir: Path, development_root: Path) -> None:
    """由持有 prepare lock 的启动器调用；只登记实际已确认的组件及固定缓存根。"""
    root = development_root.resolve()
    references = source_references(var_dir.resolve())
    if references is None:
        raise ValueError('启动运行回执不完整')
    protected = set(references)
    # Playwright 除 GUI Chromium 外还会使用无头浏览器、编码器和 Windows 依赖检查器。
    import playwright
    metadata = Path(playwright.__file__).parent / 'driver/package/browsers.json'
    browsers = json.loads(metadata.read_text(encoding='utf-8'))['browsers']
    for item in browsers:
        if item['name'] in {'chromium','chromium-headless-shell','ffmpeg','winldd'}:
            path = root / 'tools/playwright' / (item['name'].replace('-','_') + '-' + item['revision'])
            if path.is_dir():
                protected.add(path)

    def mark(path, kind, name):
        if not safe_tree(path, root):
            return
        destination = path / '.startup-owned.json'
        temporary = destination.with_suffix('.tmp')
        temporary.write_text(json.dumps({'schema_version':'1','kind':kind,'name':name}), encoding='utf-8')
        os.replace(temporary, destination)

    for path in protected:
        if path.is_relative_to(root / 'tools'):
            parts = path.relative_to(root).parts
            if len(parts) >= 3:
                component = root.joinpath(*parts[:3])
                mark(component, 'startup-component', component.name)
    for name in ('uv','pnpm-store','vite','downloads'):
        cache = root / 'cache' / name
        if cache.is_dir():
            mark(cache, 'startup-cache', name)
    directory = root / 'state/startup-instances'
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (hashlib.sha256(str(var_dir.resolve()).casefold().encode()).hexdigest()+'.json')
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps({'schema_version':'1','kind':'startup-instance','var_dir':str(var_dir.resolve()),
                                    'paths':[str(path) for path in protected]}), encoding='utf-8')
    os.replace(temporary,destination)
