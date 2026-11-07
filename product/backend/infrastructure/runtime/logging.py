# 运行日志配置
# 配置结构化 formatter、统一时间和字段、输出前执行脱敏
# 原始异常对象和秘密不得绕过 formatter 进入 stderr；日志配置不改变业务错误语义。

from __future__ import annotations

import json
import logging as stdlib_logging
import sys
import re
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import uuid4
from logging.handlers import RotatingFileHandler
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Sequence
from typing import TextIO

from product.backend.domain.redaction import redact_known_secrets
from product.backend.infrastructure.runtime.paths import RuntimePaths
from product.backend.infrastructure.runtime.generated_files import register_generated_file

_request_trace: ContextVar[str | None] = ContextVar("request_trace", default=None)


def request_trace_id(supplied: str | None) -> str:
    """外部关联只接受短标识；无效值不回显到响应或日志。"""
    return supplied if supplied and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", supplied) else f"tr_{uuid4().hex}"


@contextmanager
def request_log_context(trace_id: str):
    token = _request_trace.set(trace_id)
    try:
        yield
    finally:
        _request_trace.reset(token)


class OwnedRotatingFileHandler(RotatingFileHandler):
    """轮换产生的历史文件由日志写入者登记，清理器无需猜测名称。"""
    def __init__(self, var_dir: Path, filename: Path, **kwargs):
        self.var_dir = var_dir
        super().__init__(filename, **kwargs)
        register_generated_file(var_dir, filename, 'app-log')

    def doRollover(self):
        super().doRollover()
        for index in range(self.backupCount+1):
            path=Path(self.baseFilename + (f'.{index}' if index else ''))
            if path.is_file():
                register_generated_file(self.var_dir,path,'app-log')


class JsonFormatter(stdlib_logging.Formatter):
    def __init__(
        self,
        *,
        default_trace_id: str | None = None,
        known_secrets: Sequence[str] = (),
    ) -> None:
        super().__init__()
        self.default_trace_id = default_trace_id
        self.known_secrets = tuple(secret for secret in known_secrets if secret)

    def format(self, record: stdlib_logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "trace_id": getattr(record, "trace_id", _request_trace.get() or self.default_trace_id),
            "run_id": getattr(record, "run_id", None),
            "job_id": getattr(record, "job_id", None),
            "case_id": getattr(record, "case_id", None),
            "event_code": getattr(record, "event_code", None),
            "message": record.getMessage(),
        }
        # 生命周期日志只接受固定阶段与数值，不透传可能含凭据或业务正文的任意 extra。
        event = payload["event_code"]
        if type(event) is str and event in {"STARTUP_STAGE_COMPLETED", "STARTUP_MAINTENANCE_FAILED", "BROWSER_OPEN_COMPLETED"}:
            elapsed = getattr(record, "elapsed_ms", None)
            if type(elapsed) in (int, float) and 0 <= elapsed <= sys.float_info.max:
                payload["elapsed_ms"] = elapsed
            stage = getattr(record, "stage", None)
            if event != "BROWSER_OPEN_COMPLETED" and type(stage) is str and stage in {
                "http_import", "application_assembly", "worker_start", "startup_maintenance",
            }:
                payload["stage"] = stage
            opened = getattr(record, "opened", None)
            if event == "BROWSER_OPEN_COMPLETED" and type(opened) is bool:
                payload["opened"] = opened
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(
            redact_known_secrets(payload, self.known_secrets),
            ensure_ascii=False,
            separators=(",", ":"),
        )


def configure_logging(
    level: str = "INFO",
    *,
    stream: TextIO | None = None,
    trace_id: str | None = None,
    var_dir: Path | None = None,
    console: bool | None = None,
    known_secrets: Sequence[str] = (),
) -> stdlib_logging.Logger:
    """初始化界鉴命名日志器；控制台与 VarDir 文件 sink 可独立选择。"""

    logger = stdlib_logging.getLogger("jiejian")
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    formatter = JsonFormatter(
        default_trace_id=trace_id,
        known_secrets=known_secrets,
    )
    if console is None:
        console = stream is not None
    if console:
        stderr_handler = stdlib_logging.StreamHandler(stream or sys.stderr)
        stderr_handler.setFormatter(formatter)
        logger.addHandler(stderr_handler)
    if var_dir is not None:
        log_path = RuntimePaths(Path(var_dir)).app_logs / "jiejian.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = OwnedRotatingFileHandler(
            Path(var_dir), log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    logger.setLevel(level.upper())
    logger.propagate = False
    return logger
