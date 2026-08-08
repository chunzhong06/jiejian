"""默认脱敏的最小 JSON 结构化日志初始化。"""

from __future__ import annotations

import json
import logging as stdlib_logging
import sys
from datetime import UTC, datetime
from typing import TextIO

from .redaction import redact


class JsonFormatter(stdlib_logging.Formatter):
    def __init__(self, *, default_trace_id: str | None = None) -> None:
        super().__init__()
        self.default_trace_id = default_trace_id

    def format(self, record: stdlib_logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "trace_id": getattr(record, "trace_id", self.default_trace_id),
            "run_id": getattr(record, "run_id", None),
            "case_id": getattr(record, "case_id", None),
            "event_code": getattr(record, "event_code", None),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(redact(payload), ensure_ascii=False, separators=(",", ":"))


def configure_logging(
    level: str = "INFO",
    *,
    stream: TextIO | None = None,
    trace_id: str | None = None,
) -> stdlib_logging.Logger:
    """初始化并返回界鉴命名日志器，不改写第三方根日志器。"""

    logger = stdlib_logging.getLogger("jiejian")
    logger.handlers.clear()
    handler = stdlib_logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter(default_trace_id=trace_id))
    logger.addHandler(handler)
    logger.setLevel(level.upper())
    logger.propagate = False
    return logger
