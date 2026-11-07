# 验证进程运行时中的运行日志。

from __future__ import annotations

import pytest

import json
from logging.handlers import RotatingFileHandler
from io import StringIO

from product.backend.infrastructure.runtime.logging import configure_logging
from product.backend.interfaces.worker.job import _RedactingTextStream
from product.backend.domain.redaction import REDACTED


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


def test_startup_timings_retain_only_bounded_lifecycle_facts() -> None:
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream)
    logger.info("loaded", extra={"event_code": "STARTUP_STAGE_COMPLETED",
        "stage": "http_import", "elapsed_ms": 123.5, "request_body": "private-body"})
    logger.info("browser", extra={"event_code": "BROWSER_OPEN_COMPLETED",
        "elapsed_ms": 0, "opened": False, "stage": "http_import"})
    logger.info("ordinary", extra={"stage": "http_import", "elapsed_ms": 3, "opened": True})
    loaded, browser, ordinary = map(json.loads, stream.getvalue().splitlines())
    assert (loaded["stage"], loaded["elapsed_ms"]) == ("http_import", 123.5)
    assert (browser["opened"], browser["elapsed_ms"]) == (False, 0)
    assert "stage" not in browser
    assert not {"stage", "elapsed_ms", "opened"} & ordinary.keys()
    assert "private-body" not in stream.getvalue()


@pytest.mark.parametrize("elapsed", [True, -1, float("nan"), float("inf"), "12", None])
@pytest.mark.parametrize("stage", ["token=not-a-stage", ["http_import"], None])
def test_invalid_timing_fields_cannot_break_or_expand_logging(elapsed, stage) -> None:
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream)
    logger.info("invalid", extra={"event_code": "STARTUP_STAGE_COMPLETED",
        "stage": stage, "elapsed_ms": elapsed, "opened": "token=private"})
    payload = json.loads(stream.getvalue())
    assert not {"stage", "elapsed_ms", "opened"} & payload.keys()


def test_browser_status_keeps_boolean_only_and_timings_remain_redacted() -> None:
    stream = StringIO()
    logger = configure_logging("INFO", stream=stream, known_secrets=("http_import",))
    logger.info("loaded", extra={"event_code": "STARTUP_STAGE_COMPLETED",
        "stage": "http_import", "elapsed_ms": 1})
    logger.info("browser", extra={"event_code": "BROWSER_OPEN_COMPLETED", "opened": 1})
    loaded, browser = map(json.loads, stream.getvalue().splitlines())
    assert "http_import" not in stream.getvalue()
    assert "opened" not in browser
    assert loaded["elapsed_ms"] == 1


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

pytestmark = [pytest.mark.level3]
