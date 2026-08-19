from __future__ import annotations

import json
from io import StringIO

from product.backend.infra.runtime.logging import configure_logging
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
        "case_id",
        "event_code",
        "message",
    }
    assert default_payload["level"] == "INFO"
    assert default_payload["component"] == "jiejian"
    assert default_payload["trace_id"] == "default-trace"
    assert override_payload["trace_id"] == "record-trace"


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
    file_lines = (tmp_path / "logs" / "jiejian.log").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event_code"] for line in file_lines] == ["TEST_ONCE", "TEST_TWICE"]
