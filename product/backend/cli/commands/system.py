# System CLI 命令组
# 启动本地控制面并执行无目标副作用诊断，统一映射启动失败与退出码。

from __future__ import annotations

import time
import os
import logging
from enum import StrEnum
from pathlib import Path

import typer

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.diagnostics import run_doctor
from product.backend.cli.bootstrap import application_scope, default_frontend_dir, runtime_settings
from product.backend.cli.presentation import emit_command, emit_doctor, fail

logger = logging.getLogger("jiejian.cli.system")


class ServeReadinessStatus(StrEnum):
    """Python 端持有的服务就绪与浏览器打开事实。"""

    STARTUP_STILL_WAITING = "still-starting"
    READY_BROWSER_OPENED = "ready-browser-opened"
    READY_BROWSER_OPEN_FAILED = "ready-browser-open-failed"
    SERVER_STOPPED_BEFORE_READY = "startup-failed"


def _wait_for_ready(
    server,
    host: str,
    port: int,
    *,
    client_factory=None,
    open_browser=None,
    soft_wait_seconds: float = 10.0,
    poll_interval_seconds: float = 0.05,
    status_callback=None,
    stopped_event=None,
    monotonic=time.monotonic,
    sleeper=time.sleep,
) -> ServeReadinessStatus:
    """持续等待真实 /ready；软阈值只报告仍在启动，不形成失败结论。"""

    if client_factory is None:
        import httpx

        client_factory = lambda: httpx.Client(
            follow_redirects=False,
            trust_env=False,
            timeout=0.5,
        )
    else:
        import httpx
    open_browser = open_browser or __import__("webbrowser").open
    browser_host = f"[{host}]" if ":" in host else host
    soft_deadline = monotonic() + soft_wait_seconds
    waiting_reported = False
    with client_factory() as client:
        while True:
            if (
                (stopped_event is not None and stopped_event.is_set())
                or getattr(server, "should_exit", False)
            ):
                return ServeReadinessStatus.SERVER_STOPPED_BEFORE_READY
            if getattr(server, "started", False):
                try:
                    response = client.get(
                        f"http://{browser_host}:{port}/ready",
                        headers={"Accept": "application/json"},
                    )
                    if response.status_code != 200:
                        payload = None
                    else:
                        payload = response.json()
                    if isinstance(payload, dict) and (
                        payload.get("schema_version") == "1"
                        and payload.get("status") == "ready"
                    ):
                        browser_started = monotonic()
                        opened = bool(open_browser(f"http://{browser_host}:{port}/"))
                        logger.info(
                            "browser open completed",
                            extra={
                                "component": "serve",
                                "event_code": "BROWSER_OPEN_COMPLETED",
                                "elapsed_ms": round(
                                    (monotonic() - browser_started) * 1_000,
                                    3,
                                ),
                                "opened": opened,
                            },
                        )
                        return (
                            ServeReadinessStatus.READY_BROWSER_OPENED
                            if opened
                            else ServeReadinessStatus.READY_BROWSER_OPEN_FAILED
                        )
                except (httpx.HTTPError, OSError, ValueError, UnicodeError):
                    pass
            if not waiting_reported and monotonic() >= soft_deadline:
                waiting_reported = True
                if status_callback is not None:
                    status_callback(ServeReadinessStatus.STARTUP_STILL_WAITING)
            sleeper(poll_interval_seconds)


def serve_command(
    context: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", hidden=True),
    port: int = typer.Option(8765, "--port", min=1, max=65535, hidden=True),
    open_browser: bool = typer.Option(False, "--open/--no-open", hidden=True),
    frontend_dir: Path | None = typer.Option(
        None, "--frontend-dir", hidden=True
    ),
    official_sample_root: Path | None = typer.Option(
        None,
        "--official-sample-root",
        hidden=True,
    ),
) -> None:
    """启动本地回环 API、Worker 和前端静态资源。"""

    import ipaddress
    import threading
    import webbrowser

    import uvicorn

    try:
        address = ipaddress.ip_address(host)
        if str(address) != "127.0.0.1":
            raise JiejianError(
                ErrorCode.API_BINDING_REJECTED,
                "API 当前只允许绑定 127.0.0.1",
            )
        settings = runtime_settings(context)
        from product.backend.infra.runtime.serve_lock import ServeLock

        serve_lock = ServeLock.acquire(settings.var_dir)
        previous_lock_path = os.environ.get("JIEJIAN_SERVE_LOCK_PATH")
        previous_owner_token = os.environ.get("JIEJIAN_SERVE_OWNER_TOKEN")
        os.environ["JIEJIAN_SERVE_LOCK_PATH"] = str(serve_lock.path)
        os.environ["JIEJIAN_SERVE_OWNER_TOKEN"] = serve_lock.owner_token
        frontend_dir = (frontend_dir or default_frontend_dir()).resolve()
        from product.backend.api import create_app

        try:
            if not frontend_dir.is_dir() or not (frontend_dir / "index.html").is_file():
                raise JiejianError(ErrorCode.SERVE_FAILED, "前端静态资源缺少可读的 index.html")
            server_holder: dict[str, object] = {}

            def request_shutdown() -> None:
                server_instance = server_holder.get("server")
                if server_instance is not None:
                    setattr(server_instance, "should_exit", True)

            api = create_app(
                settings.var_dir,
                control_origin=f"http://127.0.0.1:{port}",
                frontend_dir=frontend_dir,
                shutdown_callback=request_shutdown,
                official_sample_root=official_sample_root,
            )
            config = uvicorn.Config(
                api, host=host, port=port, log_level=settings.log_level.lower()
            )
            server = uvicorn.Server(config)
            server_holder["server"] = server
            ready_thread = None
            stopped_event = threading.Event()
            if open_browser:
                def open_when_ready() -> None:
                    status = _wait_for_ready(
                        server,
                        host,
                        port,
                        open_browser=webbrowser.open,
                        status_callback=lambda value: print(
                            f"__JIEJIAN_SERVE_STATUS__:{value.value}",
                            flush=True,
                        ),
                        stopped_event=stopped_event,
                    )
                    print(f"__JIEJIAN_SERVE_STATUS__:{status.value}", flush=True)

                ready_thread = threading.Thread(
                    target=open_when_ready,
                    daemon=True,
                )
                ready_thread.start()
            try:
                server.run()
            finally:
                stopped_event.set()
                if ready_thread is not None:
                    ready_thread.join(timeout=1.0)
        finally:
            if previous_lock_path is None:
                os.environ.pop("JIEJIAN_SERVE_LOCK_PATH", None)
            else:
                os.environ["JIEJIAN_SERVE_LOCK_PATH"] = previous_lock_path
            if previous_owner_token is None:
                os.environ.pop("JIEJIAN_SERVE_OWNER_TOKEN", None)
            else:
                os.environ["JIEJIAN_SERVE_OWNER_TOKEN"] = previous_owner_token
            serve_lock.release()
    except JiejianError as exc:
        fail(exc)
    except Exception:
        logger.exception(
            "本地服务启动失败",
            extra={"component": "serve", "event_code": "SERVE_UNEXPECTED_ERROR"},
        )
        fail(JiejianError(ErrorCode.SERVE_FAILED, "本地服务启动失败；详细原因已写入日志"))


def doctor_command(
    context: typer.Context,
) -> None:
    options = context.obj
    overrides = {
        "var_dir": options.var_dir,
        "trace_id": options.trace_id,
    }
    report = run_doctor(cli_overrides=overrides)
    emit_command("system-doctor", report, human=lambda: emit_doctor(report))
    raise typer.Exit(code=0 if report.ok else 1)


def _maintenance_operation(
    context: typer.Context,
    operation: str,
    confirm: bool,
) -> None:
    try:
        with application_scope(context, environ=os.environ) as application:
            result = application.maintenance.operate(
                operation,
                confirmed=confirm,
                dry_run=not confirm,
            )
        emit_command("system-maintenance", result)
    except JiejianError as exc:
        fail(exc)


def maintenance_clean_assistant_command(
    context: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="确认清空 AI 辅助缓存"),
) -> None:
    """预览或清空 AI 辅助缓存。"""

    _maintenance_operation(context, "clear-assistant-cache", confirm)


def maintenance_clean_logs_command(
    context: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="确认清理历史运行日志"),
) -> None:
    """预览或清理当前会话开始前的历史运行日志。"""

    _maintenance_operation(context, "clear-logs", confirm)


def maintenance_clean_temporary_command(
    context: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="确认清理临时运行文件"),
) -> None:
    """预览或清理无活跃所有者的临时运行文件。"""

    _maintenance_operation(context, "clear-temporary", confirm)


def maintenance_clean_all_command(
    context: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="确认清理全部可删除内容"),
) -> None:
    """预览或清理缓存、历史日志和临时文件，不修复运行环境。"""

    _maintenance_operation(context, "clear-all", confirm)


def maintenance_repair_command(
    context: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="确认修复已标记损坏的运行环境"),
) -> None:
    """预览或修复损坏运行环境，不清理其他本地运行数据。"""

    _maintenance_operation(context, "repair-runtime", confirm)
