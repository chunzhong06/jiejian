from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from product.backend import __version__
from product.backend.infrastructure.runtime.diagnostics import runtime_environment_details
from product.backend.infrastructure.runtime.frontend_assets import frontend_asset_identity


class SystemRuntimeView:
    """日常状态只读轻量事实；完整核对是带时间的展示快照，不参与安全门禁。"""

    def __init__(self, frontend_dir: Path | None, worker_status):
        self.frontend_dir = frontend_dir
        self.worker_status = worker_status
        self._snapshot: dict | None = None
        self._build_stamp: tuple | None = None
        self._lock = Lock()

    def _stamp(self) -> tuple:
        if self.frontend_dir is None:
            return ()
        values = [str(self.frontend_dir)]
        for name in ('frontend-manifest.json', 'index.html'):
            try:
                stat = (self.frontend_dir / name).stat()
                values.append((stat.st_mtime_ns, stat.st_size))
            except OSError:
                values.append(None)
        return tuple(values)

    def summary(self) -> dict:
        browser = os.environ.get('JIEJIAN_PLAYWRIGHT_EXECUTABLE')
        if not browser and self._snapshot:
            browser = self._snapshot['environment']['playwright'].get('chromium_executable')
        return {
            'version': __version__, 'api': 'available', **self.worker_status(),
            'browser': ('available' if Path(browser).is_file() else 'unavailable') if browser else 'unknown',
            'checked_at': self._snapshot['checked_at'] if self._snapshot else None,
            'diagnostics_stale': self._snapshot is None or self._stamp() != self._build_stamp,
        }

    def inspect(self, *, refresh: bool = False) -> dict:
        with self._lock:
            stamp = self._stamp()
            if refresh or self._snapshot is None or stamp != self._build_stamp:
                self._snapshot = {
                    'environment': runtime_environment_details(),
                    'frontend_identity': frontend_asset_identity(self.frontend_dir),
                    'checked_at': datetime.now(timezone.utc).isoformat(),
                }
                self._build_stamp = stamp
            snapshot = self._snapshot
            environment = snapshot['environment']
            components = [
                {'key': 'worker', 'label': '执行服务', 'ready': self.worker_status()['worker'] == 'running'},
                {'key': 'browser', 'label': '检查浏览器', 'ready': environment['playwright']['status'] == 'available'},
                {'key': 'python', 'label': '产品运行环境', 'ready': bool(environment['python'].get('ok'))},
                {'key': 'frontend', 'label': '界面资源', 'ready': snapshot['frontend_identity']['status'] == 'CONFIRMED'},
            ]
            # 公共诊断从白名单构造，不对包含路径、配置和异常正文的环境字典做事后过滤。
            lines = [f'界鉴 {__version__}', f'系统：{platform.system()} {platform.release()}',
                     f'核对时间：{snapshot["checked_at"]}',
                     '运行方式：' + ('便携版' if environment['runtime_mode'] == 'portable' else '源码运行')]
            lines.extend(f'{item["label"]}：' + ('可用' if item['ready'] else '需要检查') for item in components)
            return {
                **self.summary(), 'components': components,
                'checked_at': snapshot['checked_at'],
                'runtime_mode': environment['runtime_mode'],
                'frontend_identity': snapshot['frontend_identity'],
                'summary_text': '\n'.join(lines),
            }
