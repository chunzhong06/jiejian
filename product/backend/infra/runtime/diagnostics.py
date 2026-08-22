# =============================================================================
# 本地环境诊断
#
# 定位
#   doctor 命令使用的无目标网络副作用运行时检查边界
#
# 职责
#   检查 Python 和依赖｜探测本地端口与 SQLite｜脱敏诊断输出
#
# 边界
#   不扫描目标、不访问公网、不修改产品数据；探针失败只形成诊断结果。
#
# 调用链
#   CLI doctor → run_doctor → local runtime probes
# =============================================================================

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import socket
import subprocess
import sqlite3
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from product.backend.core.errors import JiejianError
from product.backend.core.redaction import redact
from product.backend.infra.runtime.settings import Settings, load_settings
from product.backend.infra.runtime.logging import configure_logging
from product.backend.infra.runtime.environment_identity import (
    SUPPORTED_PYTHON,
    python_environment_report,
)


class DoctorCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1"
    name: str
    required: bool
    ok: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DoctorReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1"
    ok: bool
    checks: tuple[DoctorCheck, ...]


def _python_check() -> DoctorCheck:
    environment = python_environment_report()
    ok = sys.version_info[:2] == SUPPORTED_PYTHON and bool(environment["ok"])
    if sys.version_info[:2] != SUPPORTED_PYTHON:
        message = "需要 CPython 3.13"
    elif not environment["ok"]:
        message = "Python 环境来源异常：" + "；".join(environment["issues"])
    else:
        message = "Python 版本与环境来源符合要求"
    return DoctorCheck(
        name="python",
        required=True,
        ok=ok,
        message=message,
        details=environment,
    )


def _toolchain_requirements(project_root: Path) -> tuple[str, str, str] | None:
    package_path = project_root / "product" / "frontend" / "package.json"
    manifest_path = project_root / "product" / "config" / "toolchain.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_range = str(manifest["node"]["development_range"])
        manifest_pnpm = str(manifest["pnpm"]["version"])
        manifest_uv = str(manifest["uv"]["version"])
    except (OSError, KeyError, TypeError, ValueError):
        return None
    if package_path.is_file():
        try:
            package = json.loads(package_path.read_text(encoding="utf-8"))
            if (
                str(package["engines"]["node"]) != manifest_range
                or str(package["packageManager"]) != f"pnpm@{manifest_pnpm}"
            ):
                return None
        except (OSError, KeyError, TypeError, ValueError):
            return None
    return manifest_range, manifest_pnpm, manifest_uv


def _local_tool_check(
    *, name: str, executable_name: str, required: bool,
    project_root: Path,
) -> DoctorCheck:
    requirements = _toolchain_requirements(project_root)
    if requirements is None:
        return DoctorCheck(
            name=name,
            required=required,
            ok=False,
            message="工具链清单与前端版本真源不一致",
        )
    expected_value = requirements[1] if name == "pnpm" else requirements[0]
    environment_key = (
        "JIEJIAN_NODE_EXECUTABLE" if name == "node" else "JIEJIAN_PNPM_EXECUTABLE"
    )
    executable = os.environ.get(environment_key)
    if not executable and required:
        executable = shutil.which(executable_name)
    if not executable:
        return DoctorCheck(
            name=name,
            required=required,
            ok=not required,
            message=(
                f"未找到 {name} 可执行文件"
                if required
                else f"发布运行不需要 {name}"
            ),
            details={"expected": expected_value},
        )
    path = Path(executable).resolve()
    frontend_root = project_root / "product" / "frontend"
    try:
        # Corepack 根据当前目录的 packageManager 选择 pnpm；从仓库根探测会误用其他版本。
        completed = subprocess.run(
            [str(path), "--version"],
            cwd=frontend_root,
            capture_output=True,
            check=False,
            timeout=3,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=os.environ.copy(),
        )
    except (OSError, subprocess.SubprocessError):
        completed = None
    output = ""
    if completed is not None and completed.returncode == 0:
        output = next(
            (line.strip() for line in reversed(completed.stdout.splitlines()) if line.strip()),
            "",
        )
    if name == "node":
        import re

        match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", output)
        range_match = re.fullmatch(r">=\s*(\d+)\.(\d+)\.(\d+)\s*<\s*(\d+)", expected_value)
        ok = bool(match and range_match)
        if ok:
            actual = tuple(int(match.group(index)) for index in range(1, 4))
            minimum = tuple(int(range_match.group(index)) for index in range(1, 4))
            ok = actual >= minimum and actual[0] < int(range_match.group(4))
    else:
        ok = output == expected_value
    return DoctorCheck(
        name=name,
        required=required,
        ok=ok,
        message=(f"{name} 版本符合 package.json" if ok else f"{name} 版本不符合 package.json"),
        details={"version": output or None, "path": str(path), "expected": expected_value},
    )


def _uv_check(project_root: Path) -> DoctorCheck:
    requirements = _toolchain_requirements(project_root)
    expected = requirements[2] if requirements else None
    executable = os.environ.get("JIEJIAN_UV_EXECUTABLE")
    actual = os.environ.get("JIEJIAN_UV_VERSION")
    path = Path(executable).resolve() if executable else None
    ok = bool(expected and actual == expected and path and path.is_file())
    return DoctorCheck(
        name="uv",
        required=True,
        ok=ok,
        message="uv 版本与工具链清单一致" if ok else "uv 运行时未被启动器完整确认",
        details={
            "version": actual,
            "path": str(path) if path else None,
            "expected": expected,
        },
    )


def _frontend_check(runtime_mode: str) -> DoctorCheck:
    if runtime_mode == "release":
        root = os.environ.get("JIEJIAN_FRONTEND_DIST")
        index = Path(root).resolve() / "index.html" if root else None
        ok = bool(index and index.is_file())
        return DoctorCheck(
            name="frontend",
            required=True,
            ok=ok,
            message="预构建图形界面可用" if ok else "正式发布缺少预构建图形界面",
            details={"dist": str(index.parent) if index else None, "mode": "prebuilt"},
        )
    detail = os.environ.get("JIEJIAN_FRONTEND_DEPENDENCIES")
    ok = bool(detail)
    return DoctorCheck(
        name="frontend",
        required=True,
        ok=ok,
        message="开发前端依赖已确认" if ok else "开发前端依赖尚未同步",
        details={"state": detail, "mode": "development"},
    )


def _dependency_check() -> DoctorCheck:
    installed: dict[str, str] = {}
    missing: list[str] = []
    for package in ("httpx", "PyYAML", "pydantic", "typer"):
        try:
            installed[package] = version(package)
        except PackageNotFoundError:
            missing.append(package)
    return DoctorCheck(
        name="dependencies",
        required=True,
        ok=not missing,
        message="必要依赖可用" if not missing else "缺少必要依赖",
        details={"installed": installed, "missing": missing},
    )


def _config_check(
    config_path: Path | None, cli_overrides: dict[str, Any]
) -> tuple[DoctorCheck, Settings | None]:
    try:
        loaded = load_settings(config_path=config_path, cli_overrides=cli_overrides)
    except JiejianError as exc:
        return (
            DoctorCheck(
                name="config",
                required=True,
                ok=False,
                message="配置加载失败",
                details={"error": exc.to_dict()},
            ),
            None,
        )
    return (
        DoctorCheck(
            name="config",
            required=True,
            ok=True,
            message="配置加载成功",
            details={"schema_version": loaded.settings.schema_version},
        ),
        loaded.settings,
    )


def _var_check(settings: Settings | None) -> DoctorCheck:
    if settings is None:
        return DoctorCheck(
            name="var_dir",
            required=True,
            ok=False,
            message="配置不可用，无法检查运行目录",
        )

    path = settings.var_dir.resolve()
    temporary_path: Path | None = None
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path, prefix=".jiejian-doctor-", delete=False
        ) as stream:
            stream.write(b"doctor")
            temporary_path = Path(stream.name)
        temporary_path.unlink()
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        return DoctorCheck(
            name="var_dir",
            required=True,
            ok=False,
            message="运行目录不可写",
            details={"reason": type(exc).__name__},
        )
    return DoctorCheck(
        name="var_dir",
        required=True,
        ok=True,
        message="运行目录可写",
    )


def _sqlite_check() -> DoctorCheck:
    try:
        with tempfile.TemporaryDirectory(prefix="jiejian-doctor-") as directory:
            database = Path(directory) / "doctor.sqlite3"
            connection = sqlite3.connect(database)
            try:
                journal_mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                connection.execute("PRAGMA foreign_keys=ON")
                foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
                connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
                connection.execute(
                    "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"
                )
                constraint_enforced = False
                try:
                    connection.execute("INSERT INTO child(parent_id) VALUES (1)")
                except sqlite3.IntegrityError:
                    constraint_enforced = True
            finally:
                connection.rollback()
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.close()
        ok = journal_mode.lower() == "wal" and foreign_keys == 1 and constraint_enforced
    except (OSError, sqlite3.Error) as exc:
        return DoctorCheck(
            name="sqlite",
            required=True,
            ok=False,
            message="SQLite 能力检查失败",
            details={"reason": type(exc).__name__},
        )
    return DoctorCheck(
        name="sqlite",
        required=True,
        ok=ok,
        message="SQLite WAL 与外键可用" if ok else "SQLite WAL 或外键不可用",
        details={"journal_mode": journal_mode, "foreign_keys": bool(foreign_keys)},
    )


def _playwright_check() -> DoctorCheck:
    package_version: str | None = None
    executable: str | None = None
    reason: str | None = None
    available = False
    try:
        package_version = version("playwright")
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        try:
            chromium = Path(playwright.chromium.executable_path)
            executable = str(chromium.resolve())
            available = chromium.is_file()
        finally:
            playwright.stop()
    except (PackageNotFoundError, OSError, RuntimeError) as exc:
        reason = type(exc).__name__
    return DoctorCheck(
        name="playwright",
        required=True,
        ok=available,
        message=(
            "Playwright 与 Chromium 可用"
            if available
            else "Playwright 或 Chromium 不可用"
        ),
        details={
            "package_version": package_version,
            "chromium_executable": executable,
            "reason": reason,
        },
    )


def browser_availability() -> str:
    """Probe the local Playwright executable path without launching Chromium."""

    try:
        version("playwright")
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        try:
            executable = Path(playwright.chromium.executable_path)
            return "available" if executable.is_file() else "unavailable"
        finally:
            playwright.stop()
    except PackageNotFoundError:
        return "unavailable"
    except (OSError, RuntimeError):
        return "unknown"
    except Exception:
        return "unknown"


def runtime_environment_details() -> dict[str, Any]:
    """生成 GUI 可展示的当前进程环境身份，不执行浏览器或目标请求。"""

    python = python_environment_report()
    runtime_mode = str(python.get("runtime_mode") or "unknown")
    node_required = runtime_mode == "development"
    chromium = _playwright_check()
    chromium_details = dict(chromium.details)
    chromium_details["status"] = (
        "available"
        if chromium.ok
        else "unavailable"
        if chromium_details.get("reason") in {None, "PackageNotFoundError"}
        else "unknown"
    )
    return {
        "schema_version": "1",
        "runtime_mode": runtime_mode,
        "runtime_fingerprint": python.get("runtime_fingerprint"),
        "python": python,
        "uv": {
            "version": os.environ.get("JIEJIAN_UV_VERSION"),
            "executable": os.environ.get("JIEJIAN_UV_EXECUTABLE"),
            "required": True,
        },
        "node": {
            "version": os.environ.get("JIEJIAN_NODE_VERSION"),
            "executable": os.environ.get("JIEJIAN_NODE_EXECUTABLE"),
            "required": node_required,
        },
        "pnpm": {
            "version": os.environ.get("JIEJIAN_PNPM_VERSION"),
            "executable": os.environ.get("JIEJIAN_PNPM_EXECUTABLE"),
            "required": node_required,
        },
        "playwright": chromium_details,
        "frontend": {
            "mode": "development" if node_required else "prebuilt",
            "dependencies": os.environ.get("JIEJIAN_FRONTEND_DEPENDENCIES"),
            "dist": os.environ.get("JIEJIAN_FRONTEND_DIST"),
        },
    }


def _loopback_check() -> DoctorCheck:
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo("localhost", 0, type=socket.SOCK_STREAM)
        }
        loopback = sorted(
            address for address in addresses if ipaddress.ip_address(address).is_loopback
        )
    except (OSError, ValueError) as exc:
        return DoctorCheck(
            name="loopback",
            required=True,
            ok=False,
            message="本机环回地址解析失败",
            details={"reason": type(exc).__name__},
        )
    return DoctorCheck(
        name="loopback",
        required=True,
        ok=bool(loopback),
        message="本机环回地址可用" if loopback else "未解析到本机环回地址",
        details={"addresses": loopback},
    )


def _redaction_check() -> DoctorCheck:
    sentinel = "jiejian-doctor-secret"
    sample = {
        "password": sentinel,
        "authorization": f"Bearer {sentinel}",
        "message": f"token={sentinel}",
    }
    serialized = json.dumps(redact(sample), ensure_ascii=False)
    ok = sentinel not in serialized
    return DoctorCheck(
        name="redaction",
        required=True,
        ok=ok,
        message="脱敏器自检通过" if ok else "脱敏器自检失败",
    )


def run_doctor(
    *,
    config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
    project_root: Path | None = None,
) -> DoctorReport:
    """执行启动诊断；不访问公网，也不在源码树写数据库。"""

    config_check, settings = _config_check(config_path, cli_overrides or {})
    frontend_root = (project_root or Path(__file__).resolve().parents[4]).resolve()
    runtime_mode = os.environ.get("JIEJIAN_RUNTIME_MODE", "").strip().lower()
    node_required = runtime_mode == "development"
    checks: tuple[DoctorCheck, ...] = (
        _python_check(),
        _dependency_check(),
        _uv_check(frontend_root),
        _local_tool_check(
            name="node",
            executable_name="node",
            required=node_required,
            project_root=frontend_root,
        ),
        _local_tool_check(
            name="pnpm",
            executable_name="pnpm",
            required=node_required,
            project_root=frontend_root,
        ),
        _frontend_check(runtime_mode),
        config_check,
        _var_check(settings),
        _sqlite_check(),
        _playwright_check(),
        _loopback_check(),
        _redaction_check(),
    )
    report = DoctorReport(
        ok=all(check.ok for check in checks if check.required), checks=checks
    )
    logger = configure_logging(
        settings.log_level if settings is not None else "INFO",
        trace_id=settings.trace_id if settings is not None else None,
        var_dir=settings.var_dir if settings is not None else None,
        console=False,
    )
    logger.info(
        "启动环境诊断完成",
        extra={"component": "doctor", "event_code": "DOCTOR_COMPLETED"},
    )
    return report


def human_lines(report: DoctorReport) -> tuple[str, ...]:
    lines = []
    for check in report.checks:
        if check.required:
            marker = "通过" if check.ok else "失败"
        else:
            marker = "可用" if check.ok else "可选"
        lines.append(f"[{marker}] {check.name}: {check.message}")
    lines.append("必要检查全部通过" if report.ok else "存在必要检查失败")
    return tuple(lines)
