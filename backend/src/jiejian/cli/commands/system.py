# =============================================================================
# System CLI 命令组
#
# 定位
#   本地控制面启动和环境诊断的命令行边界
#
# 职责
#   管理 serve 资源｜执行无目标副作用诊断｜映射启动失败
#
# 调用链
#   Typer → serve / doctor commands → API / Runtime diagnostics
# =============================================================================

from __future__ import annotations

import time
from pathlib import Path

import typer

from ...errors import ErrorCode, JiejianError
from ...runtime.diagnostics import human_lines, run_doctor
from ..bootstrap import default_frontend_dir, runtime_settings
from ..presentation import fail


def _wait_for_ready(
    server,
    host: str,
    port: int,
    *,
    client_factory=None,
    open_browser=None,
    timeout_seconds: float = 10.0,
) -> bool:
    """Wait for the lifespan-backed ready response before opening a browser."""

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
        from ...runtime.serve_lock import ServeLock

        serve_lock = ServeLock.acquire(settings.var_dir)
        frontend_dir = (frontend_dir or default_frontend_dir()).resolve()
        from ...api import create_app

        try:
            if not frontend_dir.is_dir() or not (frontend_dir / "index.html").is_file():
                raise JiejianError(ErrorCode.SERVE_FAILED, "前端静态资源缺少可读的 index.html")
            api = create_app(settings.var_dir, frontend_dir=frontend_dir)
            config = uvicorn.Config(
                api, host=host, port=port, log_level=settings.log_level.lower()
            )
            server = uvicorn.Server(config)
            if open_browser:
                def open_when_ready() -> None:
                    _wait_for_ready(
                        server,
                        host,
                        port,
                        open_browser=webbrowser.open,
                    )

                threading.Thread(
                    target=open_when_ready,
                    daemon=True,
                ).start()
            server.run()
        finally:
            serve_lock.release()
    except JiejianError as exc:
        fail(exc)
    except Exception:
        fail(JiejianError(ErrorCode.SERVE_FAILED, "本地服务启动失败"))


def doctor_command(
    context: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="输出稳定 JSON"),
) -> None:
    """检查阶段 0 的本机运行条件。"""

    from ...runtime.diagnostics import human_lines, run_doctor

    options = context.obj
    overrides = {
        "var_dir": options.var_dir,
        "log_level": options.log_level,
        "trace_id": options.trace_id,
    }
    report = run_doctor(config_path=options.config, cli_overrides=overrides)
    if json_output:
        typer.echo(report.model_dump_json())
    else:
        for line in human_lines(report):
            typer.echo(line)
    raise typer.Exit(code=0 if report.ok else 1)
