# =============================================================================
# 本地环境诊断
#
# 定位
#   doctor 命令使用的无目标网络副作用运行时检查边界
#
# 职责
#   检查 Python 和依赖｜探测本地端口与 SQLite｜脱敏诊断输出
#
# 调用链
#   CLI doctor → run_doctor → local runtime probes
# =============================================================================

from __future__ import annotations

import ipaddress
import json
import socket
import sqlite3
import sys
import tempfile
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..errors import JiejianError
from ..redaction import redact
from .config import Settings, load_settings
from .logging import configure_logging


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
    current = sys.version_info[:3]
    ok = current >= (3, 12)
    return DoctorCheck(
        name="python",
        required=True,
        ok=ok,
        message="Python 版本满足要求" if ok else "需要 Python 3.12 或更高版本",
        details={"version": ".".join(str(part) for part in current)},
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
            executable = chromium.name
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
) -> DoctorReport:
    """执行阶段 0 诊断；不访问公网，也不在源码树写数据库。"""

    config_check, settings = _config_check(config_path, cli_overrides or {})
    checks: tuple[DoctorCheck, ...] = (
        _python_check(),
        _dependency_check(),
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
    )
    logger.info(
        "阶段 0 环境诊断完成",
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
