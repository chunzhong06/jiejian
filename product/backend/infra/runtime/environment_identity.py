# =============================================================================
# Python 环境身份诊断
#
# 定位
#   启动脚本、控制面与 Worker 之间的解释器和包来源一致性边界
#
# 职责
#   核对解释器身份｜识别用户级包来源｜生成可展示的脱敏环境报告
#
# 边界
#   不安装依赖、不切换环境；异常来源只形成明确诊断或由调用方拒绝启动。
# =============================================================================

from __future__ import annotations

import importlib.util
import os
import site
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_IDENTITY_KEYS = (
    "JIEJIAN_PYTHON_EXECUTABLE",
    "JIEJIAN_PYTHON_ENVIRONMENT_PATH",
    "JIEJIAN_PYTHON_ENVIRONMENT_TYPE",
)
_RUNTIME_PACKAGES = ("fastapi", "httpx", "playwright", "pydantic", "typer")


def python_environment_report(
    environment: Mapping[str, str] | None = None,
    *,
    package_names: Sequence[str] = _RUNTIME_PACKAGES,
) -> dict[str, Any]:
    """返回可展示且可判定的解释器、site-packages 与依赖来源报告。"""

    environ = os.environ if environment is None else environment
    executable = Path(sys.executable).resolve()
    prefix = Path(sys.prefix).resolve()
    expected_executable = _resolved_path(environ.get(_IDENTITY_KEYS[0]))
    expected_prefix = _resolved_path(environ.get(_IDENTITY_KEYS[1]))
    user_site = _resolved_path(_user_site_path())
    sys_paths = tuple(_resolved_path(value) for value in sys.path if value)
    package_origins = {
        name: _module_origin(name)
        for name in package_names
    }
    user_site_in_path = bool(
        user_site and any(_is_within(path, user_site) for path in sys_paths if path)
    )
    user_packages = tuple(
        sorted(
            name
            for name, origin in package_origins.items()
            if user_site and origin and _is_within(Path(origin), user_site)
        )
    )
    issues: list[str] = []
    if expected_executable and executable != expected_executable:
        issues.append("当前 Python 与启动阶段确认的解释器不一致")
    if expected_prefix and prefix != expected_prefix:
        issues.append("当前 Python 环境前缀与启动阶段确认结果不一致")
    if user_site_in_path or user_packages:
        issues.append("检测到 Windows 用户级 Python 包来源")
    if any(environ.get(key) for key in _IDENTITY_KEYS) and environ.get("PYTHONNOUSERSITE") != "1":
        issues.append("未启用 PYTHONNOUSERSITE 隔离")
    return {
        "schema_version": "1",
        "ok": not issues,
        "executable": str(executable),
        "version": ".".join(str(part) for part in sys.version_info[:3]),
        "prefix": str(prefix),
        "base_prefix": str(Path(sys.base_prefix).resolve()),
        "environment_type": environ.get(_IDENTITY_KEYS[2]) or _environment_type(prefix),
        "expected_executable": str(expected_executable) if expected_executable else None,
        "expected_prefix": str(expected_prefix) if expected_prefix else None,
        "user_site_enabled": bool(site.ENABLE_USER_SITE),
        "user_site_path": str(user_site) if user_site else None,
        "user_site_on_sys_path": user_site_in_path,
        "package_origins": package_origins,
        "user_site_packages": list(user_packages),
        "issues": issues,
    }


def require_python_environment(environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """拒绝解释器漂移或用户级包污染，并返回已确认的运行身份。"""

    report = python_environment_report(environment)
    if not report["ok"]:
        raise RuntimeError("；".join(report["issues"]))
    return report


def _module_origin(name: str) -> str | None:
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, AttributeError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    try:
        return str(Path(spec.origin).resolve())
    except OSError:
        return str(spec.origin)


def _user_site_path() -> str | None:
    try:
        value = site.getusersitepackages()
    except (AttributeError, OSError):
        return None
    return value if isinstance(value, str) else None


def _resolved_path(value: str | None) -> Path | None:
    if not value:
        return None
    try:
        return Path(value).resolve()
    except OSError:
        return Path(value).absolute()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def _environment_type(prefix: Path) -> str:
    if os.environ.get("CONDA_PREFIX"):
        return "Conda"
    if os.environ.get("VIRTUAL_ENV") or prefix != Path(sys.base_prefix).resolve():
        return "虚拟环境"
    return "未隔离 Python"
