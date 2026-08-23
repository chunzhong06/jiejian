# =============================================================================
# Recording 浏览器适配
#
# 定位
#   Recording Runner 内创建隔离 BrowserContext 和受控 Page 的资源边界
#
# 职责
#   每身份独立 context｜安装事件与网络控制｜按确定顺序关闭页面、context 和 browser
#
# 调用链
#   recording_process → BrowserRecordingAdapter → RecordingEventCollector / Playwright
# =============================================================================

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
    sync_playwright,
)

from product.backend.core.recording import Recording, RecordingReasonCode, RecordingState, RecordingTerminalState, transition_recording_state
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.recording import RecordingCleanupStatus, RecordingRunnerError, RecordingRunnerRequest, RecordingRunnerResultType, RecordingRunnerResult
from product.backend.infra.recording.events import RecordingEventCollector


class RecordingPage:
    """不暴露 BrowserContext、route、trace 或 storage_state 的受限页面句柄。"""

    def __init__(self, page: Page) -> None:
        self._page = page

    @property
    def url(self) -> str:
        return self._page.url

    @property
    def is_closed(self) -> bool:
        return self._page.is_closed()

    def goto(
        self,
        url: str,
        *,
        wait_until: str = "load",
        timeout_ms: float | None = None,
    ) -> None:
        self._page.goto(url, wait_until=wait_until, timeout=timeout_ms)

    def click(self, selector: str, *, timeout_ms: float | None = None) -> None:
        self._page.click(selector, timeout=timeout_ms)

    def fill(
        self,
        selector: str,
        value: str,
        *,
        timeout_ms: float | None = None,
    ) -> None:
        self._page.fill(selector, value, timeout=timeout_ms)

    def evaluate(self, expression: str, argument: Any = None) -> Any:
        return self._page.evaluate(expression, argument)

    def wait_for_timeout(self, milliseconds: float) -> None:
        self._page.wait_for_timeout(milliseconds)

    def close(self) -> None:
        self._page.close(run_before_unload=False)


class RecordingBrowserSession:
    """只向交互驱动提供按 identity 隔离的受限页面。"""

    def __init__(
        self,
        contexts: Mapping[str, BrowserContext],
        collector: RecordingEventCollector,
        *,
        capture_controlled: bool = False,
        start_requested: Callable[[], bool] = lambda: True,
        stop_requested: Callable[[], bool] = lambda: False,
        cancellation_requested: Callable[[], bool] = lambda: False,
        on_capture_started: Callable[[], None] = lambda: None,
        monotonic: Callable[[], float] = time.monotonic,
        capture_deadline: float | None = None,
    ) -> None:
        self._contexts = dict(contexts)
        self._collector = collector
        self._capture_controlled = capture_controlled
        self._start_requested = start_requested
        self._stop_requested = stop_requested
        self._cancellation_requested = cancellation_requested
        self._on_capture_started = on_capture_started
        self._monotonic = monotonic
        self._capture_deadline = capture_deadline
        self._capture_started = not capture_controlled

    @property
    def identity_ids(self) -> tuple[str, ...]:
        return tuple(self._contexts)

    def new_page(self, identity_id: str) -> RecordingPage:
        try:
            context = self._contexts[identity_id]
        except KeyError:
            raise JiejianError(
                ErrorCode.RECORD_PROTOCOL_INVALID,
                "录制身份不存在",
            ) from None
        page = context.new_page()
        self._collector.register_page(identity_id, page)
        return RecordingPage(page)

    @property
    def capture_started(self) -> bool:
        return self._capture_started

    def wait_for_capture_start(self, page: RecordingPage, identity_id: str) -> bool:
        """等待明确开始；准备阶段继续运行安全边界但不追加普通事件。"""

        if self._capture_started:
            return True
        while not self._start_requested():
            if self._cancellation_requested():
                return False
            if self._capture_deadline is not None and self._monotonic() >= self._capture_deadline:
                self._collector.check_runtime_budget(identity_id)
                raise JiejianError(
                    ErrorCode.RECORD_EVENT_BUDGET,
                    "等待开始采集超过运行时间预算",
                )
            page.wait_for_timeout(100)
        self._collector.begin_capture()
        self._capture_started = True
        self._on_capture_started()
        return True

    def stop_requested(self) -> bool:
        return self._stop_requested()


Interaction = Callable[[RecordingBrowserSession], None]


class BrowserRecordingAdapter:
    """运行一次Recording 浏览器捕获，不写数据库、trace 或最终工件。"""

    def run(
        self,
        request: RecordingRunnerRequest,
        interaction: Interaction,
        *,
        known_secrets: Sequence[str] = (),
        cancellation_requested: Callable[[], bool] = lambda: False,
        now_us: Callable[[], int] | None = None,
        capture_controlled: bool = False,
        ready_callback: Callable[[], None] = lambda: None,
        start_requested: Callable[[], bool] = lambda: True,
        started_callback: Callable[[], None] = lambda: None,
        stop_requested: Callable[[], bool] = lambda: False,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> RecordingRunnerResult:
        """运行一次有预算的录制；返回前冻结事件，并在所有出口关闭浏览器资源。"""

        clock = now_us or (lambda: time.time_ns() // 1_000)
        recording = Recording(
            recording_id=request.recording_id,
            project_id=request.project_id,
            created_at_us=request.created_at_us,
            updated_at_us=request.created_at_us,
        )
        recording = transition_recording_state(
            recording,
            RecordingState.STARTING,
            operator="RECORDING_RUNNER",
            occurred_at_us=clock(),
        )
        collector = RecordingEventCollector(
            request.target_scope,
            request.budget,
            known_secrets,
            clock,
            started_at_us=recording.started_at_us or recording.updated_at_us,
        )
        playwright: Playwright | None = None
        browser: Browser | None = None
        contexts: dict[str, BrowserContext] = {}
        result_type = RecordingRunnerResultType.FAILED
        terminal = RecordingTerminalState.FAILED
        reason = RecordingReasonCode.BROWSER_START_FAILED
        error_code = ErrorCode.RECORD_BROWSER_START_FAILED.value
        retryable = True

        try:
            if cancellation_requested():
                result_type = RecordingRunnerResultType.CANCELLED
                terminal = RecordingTerminalState.CANCELLED
                reason = RecordingReasonCode.CANCEL_REQUESTED
                error_code = ""
                retryable = False
            elif any(session.expires_at_us <= clock() for session in request.sessions):
                reason = RecordingReasonCode.SESSION_REFERENCE_EXPIRED
                error_code = ErrorCode.RECORD_SESSION_EXPIRED.value
                retryable = False
            else:
                playwright = sync_playwright().start()
                browser = playwright.chromium.launch(headless=request.headless)
                for session in request.sessions:
                    context = browser.new_context(
                        accept_downloads=False,
                        service_workers="block",
                    )
                    timeout_ms = request.target_scope.timeout_seconds * 1_000
                    context.set_default_timeout(timeout_ms)
                    context.set_default_navigation_timeout(timeout_ms)
                    collector.attach_context(session.identity_id, context)
                    contexts[session.identity_id] = context
                ready_callback()
                capture_deadline = monotonic() + request.budget.max_duration_us / 1_000_000

                def mark_capture_started() -> None:
                    nonlocal recording
                    recording = transition_recording_state(
                        recording,
                        RecordingState.RECORDING,
                        operator="RECORDING_RUNNER",
                        occurred_at_us=clock(),
                    )
                    started_callback()

                if not capture_controlled:
                    collector.begin_capture()
                    mark_capture_started()
                collector.check_runtime_budget(request.sessions[0].identity_id)
                session = RecordingBrowserSession(
                    contexts,
                    collector,
                    capture_controlled=capture_controlled,
                    start_requested=start_requested,
                    stop_requested=stop_requested,
                    cancellation_requested=cancellation_requested,
                    on_capture_started=mark_capture_started,
                    monotonic=monotonic,
                    capture_deadline=capture_deadline,
                )
                interaction(session)
                if capture_controlled and not session.capture_started and not cancellation_requested():
                    raise JiejianError(
                        ErrorCode.RECORD_INTERACTION_FAILED,
                        "录制未收到开始采集动作",
                    )
                collector.check_runtime_budget(request.sessions[0].identity_id)
                if collector.safety_error is not None:
                    result_type = RecordingRunnerResultType.SAFETY_STOPPED
                    terminal = RecordingTerminalState.SAFETY_STOPPED
                    reason = collector.safety_reason
                    error_code = ""
                    retryable = False
                elif cancellation_requested():
                    result_type = RecordingRunnerResultType.CANCELLED
                    terminal = RecordingTerminalState.CANCELLED
                    reason = RecordingReasonCode.CANCEL_REQUESTED
                    error_code = ""
                    retryable = False
                else:
                    result_type = RecordingRunnerResultType.CAPTURED
                    reason = RecordingReasonCode.RECORDING_FINISHED
                    error_code = ""
                    retryable = False
        except PlaywrightError:
            if collector.safety_error is not None:
                result_type = RecordingRunnerResultType.SAFETY_STOPPED
                terminal = RecordingTerminalState.SAFETY_STOPPED
                reason = collector.safety_reason
                error_code = ""
                retryable = False
            elif recording.state is RecordingState.STARTING:
                reason = RecordingReasonCode.BROWSER_START_FAILED
                error_code = ErrorCode.RECORD_BROWSER_START_FAILED.value
            else:
                reason = RecordingReasonCode.BROWSER_INTERACTION_FAILED
                error_code = ErrorCode.RECORD_INTERACTION_FAILED.value
        except JiejianError as exc:
            if exc.code in {
                ErrorCode.RECORD_SCOPE_BLOCKED.value,
                ErrorCode.RECORD_EVENT_BUDGET.value,
            }:
                result_type = RecordingRunnerResultType.SAFETY_STOPPED
                terminal = RecordingTerminalState.SAFETY_STOPPED
                reason = collector.safety_reason
                error_code = ""
                retryable = False
            else:
                reason = RecordingReasonCode.BROWSER_INTERACTION_FAILED
                error_code = ErrorCode.RECORD_INTERACTION_FAILED.value
                retryable = False
        except Exception:
            reason = RecordingReasonCode.BROWSER_INTERACTION_FAILED
            error_code = ErrorCode.RECORD_INTERACTION_FAILED.value
            retryable = False

        pending = None if result_type is RecordingRunnerResultType.CAPTURED else terminal
        recording = transition_recording_state(
            recording,
            RecordingState.CLEANING,
            operator="RECORDING_RUNNER",
            occurred_at_us=clock(),
            reason_code=reason,
            pending_terminal_state=pending,
        )
        collector.freeze()
        cleanup_failed = self._close(playwright, browser, tuple(contexts.values()))
        if cleanup_failed:
            result_type = RecordingRunnerResultType.FAILED
            error_code = ErrorCode.RECORD_CLEANUP_FAILED.value
            retryable = False
            recording = transition_recording_state(
                recording,
                RecordingState.FAILED,
                operator="RECORDING_RUNNER",
                occurred_at_us=clock(),
                reason_code=RecordingReasonCode.CLEANUP_FAILED,
            )
            cleanup_status = RecordingCleanupStatus.FAILED
        elif result_type is RecordingRunnerResultType.CAPTURED:
            recording = transition_recording_state(
                recording,
                RecordingState.PROCESSING,
                operator="RECORDING_RUNNER",
                occurred_at_us=clock(),
            )
            cleanup_status = RecordingCleanupStatus.SUCCEEDED
        else:
            recording = transition_recording_state(
                recording,
                RecordingState(terminal.value),
                operator="RECORDING_RUNNER",
                occurred_at_us=clock(),
                reason_code=reason,
            )
            cleanup_status = RecordingCleanupStatus.SUCCEEDED

        return RecordingRunnerResult(
            recording_id=request.recording_id,
            project_id=request.project_id,
            finished_at_us=clock(),
            result_type=result_type,
            recording_state=recording.state,
            cleanup_status=cleanup_status,
            reason_codes=recording.reason_codes,
            state_events=recording.events,
            events=collector.events,
            error=(
                RecordingRunnerError(
                    code=error_code,
                    retryable=retryable,
                )
                if error_code
                else None
            ),
        )

    @staticmethod
    def _close(
        playwright: Playwright | None,
        browser: Browser | None,
        contexts: tuple[BrowserContext, ...],
    ) -> bool:
        failed = False
        for context in contexts:
            for page in tuple(context.pages):
                try:
                    if not page.is_closed():
                        page.close(run_before_unload=False)
                except Exception:
                    failed = True
            try:
                context.close(reason="recording-finished")
            except Exception:
                failed = True
        if browser is not None:
            try:
                browser.close(reason="recording-finished")
            except Exception:
                failed = True
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                failed = True
        return failed
