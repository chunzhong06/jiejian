# =============================================================================
# Python 运行环境身份
#
# 定位
#   启动器、控制面与全部 Python 子进程之间的解释器和包来源信任边界
#
# 职责
#   核对解释器与 Prefix｜确认 editable 当前源码｜生成稳定指纹
#
# 边界
#   只诊断和拒绝来源漂移，不安装依赖、不切换环境，也不信任调用者 cwd。
# =============================================================================

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import json
import os
import site
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from product.backend.core.errors import ErrorCode, JiejianError

SUPPORTED_PYTHON = (3, 13)
_RUNTIME_MODES = {"development"}
_IDENTITY_KEYS = (
    "JIEJIAN_PYTHON_EXECUTABLE",
    "JIEJIAN_PYTHON_ENVIRONMENT_PATH",
    "JIEJIAN_PYTHON_ENVIRONMENT_TYPE",
)
_RUNTIME_PACKAGES = (
    "alembic",
    "fastapi",
    "httpx",
    "playwright",
    "pydantic",
    "sqlalchemy",
    "typer",
    "uvicorn",
    "yaml",
    "product",
)


def python_environment_report(
    environment: Mapping[str, str] | None = None,
    *,
    package_names: Sequence[str] = _RUNTIME_PACKAGES,
) -> dict[str, Any]:
    """返回可展示、可复算且足以拒绝解释器或包来源漂移的环境身份。"""

    environ = os.environ if environment is None else environment
    executable = Path(sys.executable).resolve()
    prefix = Path(sys.prefix).resolve()
    base_prefix = Path(sys.base_prefix).resolve()
    expected_executable = _resolved_path(environ.get(_IDENTITY_KEYS[0]))
    expected_prefix = _resolved_path(environ.get(_IDENTITY_KEYS[1]))
    project_root = _resolved_path(environ.get("JIEJIAN_PROJECT_ROOT"))
    runtime_mode = (environ.get("JIEJIAN_RUNTIME_MODE") or "").strip().lower()
    environment_type = (environ.get(_IDENTITY_KEYS[2]) or "").strip().lower()
    user_site = _resolved_path(_user_site_path())
    sys_paths = tuple(_resolved_path(value) for value in sys.path if value)
    package_origins = {name: _module_origin(name) for name in package_names}
    distribution = _project_distribution()
    product_origin = package_origins.get("product")
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
    if sys.version_info[:2] != SUPPORTED_PYTHON:
        issues.append("界鉴仅支持 CPython 3.13")
    if runtime_mode not in _RUNTIME_MODES:
        issues.append("未声明有效的界鉴运行模式")
    if expected_executable is None or expected_prefix is None:
        issues.append("启动阶段未确认 Python 解释器和环境 Prefix")
    if expected_executable and executable != expected_executable:
        issues.append("当前 Python 与启动阶段确认的解释器不一致")
    if expected_prefix and prefix != expected_prefix:
        issues.append("当前 Python 环境 Prefix 与启动阶段确认结果不一致")
    if user_site_in_path or user_packages:
        issues.append("检测到 Windows 用户级 Python 包来源")
    if environ.get("PYTHONNOUSERSITE") != "1":
        issues.append("未启用 PYTHONNOUSERSITE 隔离")

    missing_packages = sorted(name for name, origin in package_origins.items() if not origin)
    if missing_packages:
        issues.append("运行依赖不完整：" + ", ".join(missing_packages))
    for name, origin in package_origins.items():
        if not origin or name == "product":
            continue
        origin_path = Path(origin)
        if not _is_within(origin_path, prefix):
            issues.append(f"依赖 {name} 不属于当前 Python Prefix")

    editable = bool(distribution.get("editable"))
    distribution_root = _resolved_path(_string_or_none(distribution.get("root")))
    source_root = _resolved_path(_string_or_none(distribution.get("source_root")))
    product_path = _resolved_path(product_origin)
    if distribution.get("installed") is not True:
        issues.append("当前环境没有安装界鉴项目包")
    if runtime_mode == "development":
        if environment_type != "conda":
            issues.append("开发模式必须使用项目专用 Conda 环境")
        if project_root is None:
            issues.append("开发模式缺少当前仓库根目录身份")
        if not editable:
            issues.append("开发模式必须 editable 安装当前源码")
        if project_root and source_root and source_root != project_root:
            issues.append("editable 安装指向了其他源码目录")
        if project_root and product_path and not _is_within(product_path, project_root):
            issues.append("开发模式导入的 product 不属于当前仓库")

    fingerprint_payload = {
        "python": str(executable),
        "version": ".".join(str(part) for part in sys.version_info[:3]),
        "prefix": str(prefix),
        "mode": runtime_mode,
        "environment_type": environment_type,
        "product_origin": product_origin,
        "distribution": distribution,
        "package_origins": package_origins,
    }
    runtime_fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    expected_fingerprint = environ.get("JIEJIAN_RUNTIME_FINGERPRINT")
    if expected_fingerprint and expected_fingerprint != runtime_fingerprint:
        issues.append("当前 Python 包来源指纹与主进程不一致")

    return {
        "schema_version": "1",
        "ok": not issues,
        "runtime_mode": runtime_mode or None,
        "runtime_fingerprint": runtime_fingerprint,
        "expected_runtime_fingerprint": expected_fingerprint,
        "executable": str(executable),
        "version": ".".join(str(part) for part in sys.version_info[:3]),
        "prefix": str(prefix),
        "base_prefix": str(base_prefix),
        "environment_type": environment_type or _environment_type(prefix, environ),
        "expected_executable": str(expected_executable) if expected_executable else None,
        "expected_prefix": str(expected_prefix) if expected_prefix else None,
        "project_root": str(project_root) if project_root else None,
        "user_site_enabled": bool(site.ENABLE_USER_SITE),
        "user_site_path": str(user_site) if user_site else None,
        "user_site_on_sys_path": user_site_in_path,
        "sys_path": [str(path) for path in sys_paths if path],
        "package_origins": package_origins,
        "project_distribution": distribution,
        "user_site_packages": list(user_packages),
        "issues": issues,
    }


def require_python_environment(
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """拒绝解释器、安装模式、项目来源或主子进程指纹漂移。"""

    report = python_environment_report(environment)
    if not report["ok"]:
        raise JiejianError(
            ErrorCode.RUNTIME_ENVIRONMENT_INVALID,
            "界鉴 Python 运行环境不可信",
            details={
                "issues": report["issues"],
                "python": report["executable"],
                "prefix": report["prefix"],
                "runtime_mode": report["runtime_mode"],
            },
        )
    return report


def _project_distribution() -> dict[str, object]:
    try:
        distribution = importlib.metadata.distribution("jiejian")
    except importlib.metadata.PackageNotFoundError:
        return {
            "installed": False,
            "version": None,
            "root": None,
            "editable": False,
            "source_root": None,
        }
    direct_url: dict[str, object] = {}
    try:
        value = distribution.read_text("direct_url.json")
        parsed = json.loads(value) if value else {}
        if isinstance(parsed, dict):
            direct_url = parsed
    except (OSError, ValueError):
        direct_url = {}
    directory_info = direct_url.get("dir_info")
    editable = bool(
        isinstance(directory_info, dict) and directory_info.get("editable") is True
    )
    source_root = _file_url_path(direct_url.get("url"))
    return {
        "installed": True,
        "version": distribution.version,
        "root": str(Path(distribution.locate_file("")).resolve()),
        "editable": editable,
        "source_root": str(source_root) if source_root else None,
    }


def _module_origin(name: str) -> str | None:
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, AttributeError, ValueError):
        return None
    if spec is None:
        return None
    candidate = spec.origin
    if not candidate and spec.submodule_search_locations:
        candidate = next(iter(spec.submodule_search_locations), None)
    if not candidate:
        return None
    try:
        return str(Path(candidate).resolve())
    except OSError:
        return str(candidate)


def _file_url_path(value: object) -> Path | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    if parsed.scheme != "file":
        return None
    decoded = unquote(parsed.path)
    if os.name == "nt" and len(decoded) >= 3 and decoded[0] == "/" and decoded[2] == ":":
        decoded = decoded[1:]
    return _resolved_path(decoded)


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


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _environment_type(prefix: Path, environment: Mapping[str, str]) -> str:
    if environment.get("CONDA_PREFIX"):
        return "conda"
    if environment.get("VIRTUAL_ENV") or prefix != Path(sys.base_prefix).resolve():
        return "virtual"
    return "unisolated"
