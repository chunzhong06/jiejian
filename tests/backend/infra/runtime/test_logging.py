# 验证进程运行时中的运行日志。

from __future__ import annotations

import json
from logging.handlers import RotatingFileHandler
from io import StringIO

from product.backend.infra.runtime.logging import configure_logging
from product.backend.infra.runtime.worker.process import _RedactingTextStream
from product.backend.core.redaction import REDACTED


def test_json_logging_contains_required_fields_and_trace_context() -> None:
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream, trace_id="default-trace")

    logger.info("default trace")
    logger.info("record trace", extra={"trace_id": "record-trace"})

    default_payload, override_payload = [
        json.loads(line) for line in stream.getvalue().splitlines()
    ]
    assert set(default_payload) == {
        "timestamp",
        "level",
        "component",
        "trace_id",
        "run_id",
        "job_id",
        "case_id",
        "event_code",
        "message",
    }
    assert default_payload["level"] == "INFO"
    assert default_payload["component"] == "jiejian"
    assert default_payload["trace_id"] == "default-trace"
    assert override_payload["trace_id"] == "record-trace"


def test_job_context_and_known_secret_are_safe_in_console_and_main_log(tmp_path) -> None:
    stream = StringIO()
    sentinel = "worker-log-secret-sentinel"
    logger = configure_logging(
        "INFO",
        stream=stream,
        var_dir=tmp_path,
        known_secrets=(sentinel,),
    )

    try:
        raise RuntimeError(f"ordinary-{sentinel}")
    except RuntimeError:
        logger.exception(
            f"ordinary-{sentinel}",
            extra={"job_id": "job_" + "1" * 32},
        )

    main_log = (tmp_path / "logs" / "app" / "jiejian.log").read_text(encoding="utf-8")
    assert sentinel not in stream.getvalue()
    assert sentinel not in main_log
    payload = json.loads(main_log)
    assert payload["job_id"] == "job_" + "1" * 32


def test_worker_bootstrap_stream_redacts_known_secret_before_logging_initializes() -> None:
    raw = StringIO()
    sentinel = "bootstrap-secret-sentinel"
    stream = _RedactingTextStream(raw, (sentinel,))

    stream.write(f"Traceback: ordinary-{sentinel}\n")
    stream.flush()

    assert sentinel not in raw.getvalue()
    assert "[REDACTED]" in raw.getvalue()


def test_configured_log_level_filters_lower_priority_records() -> None:
    stream = StringIO()
    logger = configure_logging("WARNING", stream=stream)

    logger.info("hidden")
    logger.warning("visible")

    payloads = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [payload["message"] for payload in payloads] == ["visible"]
    assert payloads[0]["level"] == "WARNING"


def test_log_messages_and_exceptions_are_redacted() -> None:
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream)
    sentinel = "logging-secret-value"

    try:
        raise RuntimeError(f"token={sentinel}")
    except RuntimeError:
        logger.exception(f"password={sentinel}")

    serialized = stream.getvalue()
    payload = json.loads(serialized)
    assert sentinel not in serialized
    assert REDACTED in payload["message"]
    assert REDACTED in payload["error"]


def test_logging_can_append_to_var_log_without_duplicate_handlers(tmp_path) -> None:
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream, var_dir=tmp_path)
    logger.info("once", extra={"event_code": "TEST_ONCE"})
    configure_logging("INFO", stream=stream, var_dir=tmp_path)
    logger = __import__("logging").getLogger("jiejian")
    logger.info("twice", extra={"event_code": "TEST_TWICE"})

    assert [json.loads(line)["message"] for line in stream.getvalue().splitlines()] == ["once", "twice"]
    file_lines = (tmp_path / "logs" / "app" / "jiejian.log").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event_code"] for line in file_lines] == ["TEST_ONCE", "TEST_TWICE"]


def test_logging_can_keep_info_out_of_console_while_retaining_file_sink(tmp_path) -> None:
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream, var_dir=tmp_path, console=False)
    logger.info("file only", extra={"event_code": "TEST_FILE_ONLY"})

    assert stream.getvalue() == ""
    payload = json.loads(
        (tmp_path / "logs" / "app" / "jiejian.log").read_text(encoding="utf-8").strip()
    )
    assert payload["event_code"] == "TEST_FILE_ONLY"


def test_main_log_has_fixed_rotation_budget(tmp_path) -> None:
    logger = configure_logging("INFO", var_dir=tmp_path, console=False)

    handler = next(item for item in logger.handlers if isinstance(item, RotatingFileHandler))
    assert handler.maxBytes == 10 * 1024 * 1024
    assert handler.backupCount == 5
