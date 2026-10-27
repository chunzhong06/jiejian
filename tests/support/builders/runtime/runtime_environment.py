# 提供受控 Python 运行环境身份测试夹具。

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[4]


def runtime_identity_environment(
    var_dir: Path,
    *,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """构造不依赖调用终端的完整测试运行身份。"""

    environment = {
        name: os.environ[name]
        for name in ("COMSPEC", "PATHEXT", "SYSTEMROOT", "WINDIR")
        if os.environ.get(name)
    }
    environment.update(
        {
            "JIEJIAN_PYTHON_EXECUTABLE": str(Path(sys.executable).resolve()),
            "JIEJIAN_PYTHON_ENVIRONMENT_PATH": str(Path(sys.prefix).resolve()),
            "JIEJIAN_PYTHON_ENVIRONMENT_TYPE": os.environ.get(
                "JIEJIAN_PYTHON_ENVIRONMENT_TYPE", "conda"
            ),
            "JIEJIAN_PROJECT_ROOT": os.environ.get(
                "JIEJIAN_PROJECT_ROOT", str(PROJECT_ROOT)
            ),
            "JIEJIAN_RUNTIME_FINGERPRINT": os.environ.get(
                "JIEJIAN_RUNTIME_FINGERPRINT", "test-runtime-fingerprint"
            ),
            "JIEJIAN_RUNTIME_MODE": os.environ.get(
                "JIEJIAN_RUNTIME_MODE", "development"
            ),
            "JIEJIAN_VAR_DIR": str(var_dir.resolve()),
        }
    )
    environment.update(extra or {})
    return environment


def write_python_installation_contract(root: Path) -> Path:
    """只构造旧安装格式的文件契约，入口立即失败；没有业务服务或第二套示例。"""
    import json
    source=root/'source';source.mkdir(parents=True)
    (source/'server.py').write_text('# 仅用于安装及启动失败边界。\nraise RuntimeError("installation probe")\n',encoding='utf-8')
    (root/'sample.json').write_text(json.dumps(dict(schema_version='1',sample_id='collaboration-space',display_name='协作空间',
        source_root='source',entry_module='server',health_path='/health'),ensure_ascii=False),encoding='utf-8')
    return root
