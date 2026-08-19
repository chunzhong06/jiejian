# =============================================================================
# 运行日志配置
#
# 定位
#   Python logging 记录与默认脱敏 JSON 输出之间的基础设施边界
#
# 职责
#   配置结构化 formatter｜统一时间和字段｜输出前执行脱敏
#
# 边界
#   原始异常对象和秘密不得绕过 formatter 进入 stderr；日志配置不改变业务错误语义。
#
# 调用链
#   Runtime bootstrap → configure_logging → stderr JSON logs
# =============================================================================

from __future__ import annotations

import json
import logging as stdlib_logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from product.backend.core.redaction import redact


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
    var_dir: Path | None = None,
) -> stdlib_logging.Logger:
    """初始化界鉴命名日志器；日志只写 stderr 和可选的 var 日志文件。"""

    logger = stdlib_logging.getLogger("jiejian")
    for handler in tuple(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    formatter = JsonFormatter(default_trace_id=trace_id)
    stderr_handler = stdlib_logging.StreamHandler(stream or sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)
    if var_dir is not None:
        log_path = Path(var_dir).resolve() / "logs" / "jiejian.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = stdlib_logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    logger.setLevel(level.upper())
    logger.propagate = False
    return logger
