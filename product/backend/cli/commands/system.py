# System CLI 命令组
# 启动本地控制面并执行无目标副作用诊断，统一映射启动失败与退出码。

from __future__ import annotations

import time
import os
import logging
from pathlib import Path

import typer

from product.backend.core.errors import ErrorCode, JiejianError
from product.backend.infra.runtime.diagnostics import run_doctor
from product.backend.cli.bootstrap import default_frontend_dir, runtime_settings
from product.backend.cli.presentation import emit_doctor, fail, set_command_mode

logger = logging.getLogger("jiejian.cli.system")


def _wait_for_ready(
    server,
    host: str,
    port: int,
    *,
    client_factory=None,
    open_browser=None,
    timeout_seconds: float = 10.0,
) -> bool:
    """等待 lifespan 就绪响应后再打开浏览器，避免把端口监听误判为可用。"""

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
    deadline = time.monotonic() + timeout_seconds
    with client_factory() as client:
        while time.monotonic() < deadline:
            if getattr(server, "started", False):
                try:
                    response = client.get(
                        f"http://{browser_host}:{port}/ready",
                        headers={"Accept": "application/json"},
                    )
                    if response.status_code != 200:
                        time.sleep(0.05)
                        continue
                    payload = response.json()
                    if (
                        payload.get("schema_version") == "1"
                        and payload.get("status") == "ready"
                    ):
                        return bool(open_browser(f"http://{browser_host}:{port}/"))
                except (httpx.HTTPError, OSError, ValueError, UnicodeError):
                    pass
            time.sleep(0.05)
    return False


def serve_command(
    context: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port", min=1, max=65535),
    open_browser: bool = typer.Option(False, "--open/--no-open"),
    frontend_dir: Path | None = typer.Option(
        None, "--frontend-dir", help="前端 dist 静态资源目录"
    ),
) -> None:
    """启动本地回环 API、Worker 和前端静态资源。"""

    import ipaddress
    import threading
    import webbrowser

    import uvicorn

    try:
        address = ipaddress.ip_address(host)
        if not address.is_loopback:
            raise JiejianError(ErrorCode.API_BINDING_REJECTED, "API 只允许绑定本机回环地址")
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
                frontend_dir=frontend_dir,
                shutdown_callback=request_shutdown,
            )
            config = uvicorn.Config(
                api, host=host, port=port, log_level=settings.log_level.lower()
            )
            server = uvicorn.Server(config)
            server_holder["server"] = server
            if open_browser:
                def open_when_ready() -> None:
                    opened = _wait_for_ready(
                        server,
                        host,
                        port,
                        open_browser=webbrowser.open,
                    )
                    marker = "browser-opened" if opened else "browser-open-failed"
                    print(f"__JIEJIAN_SERVE_READY__:{marker}", flush=True)

                threading.Thread(
                    target=open_when_ready,
                    daemon=True,
                ).start()
            server.run()
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
    json_output: bool | None = typer.Option(
        None, "--json", help="兼容旧位置；建议使用全局 --json", hidden=True
    ),
) -> None:

    if json_output:
        set_command_mode("json")

    options = context.obj
    overrides = {
        "var_dir": options.var_dir,
        "log_level": options.log_level,
        "trace_id": options.trace_id,
    }
    report = run_doctor(config_path=options.config, cli_overrides=overrides)
    emit_doctor(report)
    raise typer.Exit(code=0 if report.ok else 1)
