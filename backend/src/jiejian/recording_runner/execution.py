# =============================================================================
# Recording Runner 进程适配
#
# 定位
#   Recording V1 协议与受控 Playwright 录制之间的独立进程边界
#
# 职责
#   严格读取请求｜运行 BrowserRecordingAdapter｜写入脱敏事件和可信结果
#
# 调用链
#   recording_runner.__main__ → execute_recording → BrowserRecordingAdapter → RecordingRunnerResultV1
# =============================================================================

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import BinaryIO, TextIO

from playwright.sync_api import Error as PlaywrightError

from ..errors import JiejianError
from ..protocols import (
    RECORDING_REQUEST_MAX_BYTES,
    RecordingRunnerRequestV1,
    canonical_recording_json_bytes,
    parse_recording_request,
)
from ..recording.browser import (
    BrowserRecordingAdapter,
    RecordingBrowserSession,
)

RECORDING_RUNNER_EXIT_OK = 0
RECORDING_RUNNER_EXIT_PROTOCOL = 64
RECORDING_RUNNER_EXIT_INTERNAL = 70
_CANCEL_PATH_ENV = "JIEJIAN_RECORDING_CANCEL_FILE"


def execute_recording_runner(
    *,
    stdin: BinaryIO,
    stdout: BinaryIO,
    stderr: TextIO,
    environ: Mapping[str, str] | None = None,
    adapter: BrowserRecordingAdapter | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> int:
    """从 stdin 读取一个请求，并只向 stdout 写一个可信结果 JSON。"""

    environment = os.environ if environ is None else environ
    try:
        raw = stdin.read(RECORDING_REQUEST_MAX_BYTES + 1)
        request = parse_recording_request(raw)
    except (JiejianError, OSError):
        stderr.write("RECORD_PROTOCOL_INVALID\n")
        return RECORDING_RUNNER_EXIT_PROTOCOL
    cancel_path = (
        Path(environment[_CANCEL_PATH_ENV])
        if environment.get(_CANCEL_PATH_ENV)
        else None
    )
    cancellation_requested = (
        cancel_path.exists if cancel_path is not None else lambda: False
    )
    try:
        result = (adapter or BrowserRecordingAdapter()).run(
            request,
            lambda session: _capture_until_closed(
                session,
                request,
                cancellation_requested,
                monotonic,
            ),
            cancellation_requested=cancellation_requested,
        )
        stdout.write(canonical_recording_json_bytes(result))
        stdout.flush()
        return RECORDING_RUNNER_EXIT_OK
    except (JiejianError, OSError):
        stderr.write("RECORD_RUNNER_FAILED\n")
        return RECORDING_RUNNER_EXIT_INTERNAL
    except Exception:
        stderr.write("RECORD_RUNNER_FATAL\n")
        return RECORDING_RUNNER_EXIT_INTERNAL


def _capture_until_closed(
    session: RecordingBrowserSession,
    request: RecordingRunnerRequestV1,
    cancellation_requested: Callable[[], bool],
    monotonic: Callable[[], float],
) -> None:
    page = session.new_page(session.identity_ids[0])
    page.goto(request.target_scope.base_url)
    deadline = monotonic() + request.budget.max_duration_us / 1_000_000
    while not page.is_closed and not cancellation_requested() and monotonic() < deadline:
        try:
            page.wait_for_timeout(100)
        except PlaywrightError:
            if page.is_closed:
                return
            raise
