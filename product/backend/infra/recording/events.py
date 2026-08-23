# =============================================================================
# Recording 事件采集
#
# 定位
#   Playwright 回调与可持久 RecordingEvent 之间的安全边界
#
# 职责
#   关联 identity/page/frame/request｜执行 TargetScope 与预算｜落盘前统一脱敏
#
# 调用链
#   BrowserRecordingAdapter → RecordingEventCollector → RecordingEvent / BoundedRouteTransport
# =============================================================================

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from playwright.sync_api import (
    BrowserContext,
    ConsoleMessage,
    Error as PlaywrightError,
    Frame,
    Page,
    Request,
    Route,
    WebError,
    WebSocketRoute,
)

from product.backend.core.recording import RecordingReasonCode
from product.protocols.web.target import WebTargetDefinition, WebTargetScope
from product.backend.core.errors import ErrorCode, JiejianError
from product.protocols.recording import RECORDING_EVENT_MAX_BYTES, RecordingBudget, RecordingEventKind, RecordingEvent
from product.backend.infra.execution.web.adapter import WebTargetGuard
from product.backend.workflows.recording.sanitization import RecordingSanitizer
from product.backend.infra.recording.transport import BoundedRouteTransport
from product.backend.infra.recording.ui_capture import install_ui_capture

_SAFETY_EVENT_RESERVE_BYTES = 768


class RecordingEventCollector:
    """连接 Playwright context，并只暴露经过授权和脱敏的 事件。"""

    def __init__(
        self,
        scope: WebTargetScope,
        budget: RecordingBudget,
        known_secrets: Sequence[str],
        now_us: Callable[[], int],
        *,
        started_at_us: int,
    ) -> None:
        self.scope = scope
        self.budget = budget
        self.now_us = now_us
        self.started_at_us = started_at_us
        self._sanitizer = RecordingSanitizer(budget, known_secrets)
        self._transport = BoundedRouteTransport(scope)
        self.events: tuple[RecordingEvent, ...] = ()
        self.safety_error: JiejianError | None = None
        self.safety_reason = RecordingReasonCode.TARGET_SCOPE_VIOLATION
        self._frozen = False
        self._capture_enabled = False
        self._payload_bytes = 0
        self._page_ids: dict[Page, str] = {}
        self._page_identity: dict[Page, str] = {}
        self._frame_ids: dict[Frame, str] = {}
        self._request_ids: dict[Request, str] = {}
        self._discarded_requests: set[Request] = set()
        self._websocket_count = 0
        self._action_count = 0
        self._pending_actions: dict[tuple[str, str, str], str] = {}
        self._guards: dict[str, WebTargetGuard] = {}

    def begin_capture(self) -> None:
        """开启持久事件采集，并丢弃准备阶段建立的关联索引。"""

        self._capture_enabled = True
        # 登录准备期间的 page/request 关联不能带入草稿；开始后由下一次事件重新建立。
        self._discarded_requests.update(self._request_ids)
        self._page_ids.clear()
        self._page_identity.clear()
        self._frame_ids.clear()
        self._request_ids.clear()
        self._pending_actions.clear()

    def freeze(self) -> None:
        """在清理前固定事件集合，避免关闭回调改变已判定结果。"""

        self._frozen = True

    def attach_context(self, identity_id: str, context: BrowserContext) -> None:
        """在创建任何 page 前为一个独立 context 安装全部网络边界。"""

        self._guards[identity_id] = WebTargetGuard(
            WebTargetDefinition(scope=self.scope, reset_path="/reset")
        )
        install_ui_capture(
            context,
            lambda source, payload: self._record_ui_action(
                identity_id,
                source,
                payload,
            ),
        )
        context.route(
            "**/*", lambda route: self._route(identity_id, context, route)
        )
        context.route_web_socket(
            "**/*", lambda route: self._websocket_route(identity_id, route)
        )
        context.on("page", lambda page: self.register_page(identity_id, page))
        context.on(
            "requestfinished",
            lambda request: self._request_finished(identity_id, request),
        )
        context.on("weberror", lambda error: self._web_error(identity_id, error))

    def register_page(
        self,
        identity_id: str,
        page: Page,
        *,
        parent_page: Page | None = None,
    ) -> None:
        """为新页面建立稳定 identity/page 关联并安装全部安全停止回调。"""

        if page in self._page_ids:
            if parent_page is not None:
                self._link_popup(page, parent_page)
            return
        page_id = f"page_{len(self._page_ids) + 1:06d}"
        self._page_ids[page] = page_id
        self._page_identity[page] = identity_id
        if len(self._page_ids) > self.budget.max_pages:
            self._stop_for_budget(identity_id, page_id)
            return
        opener = parent_page or page.opener
        parent_page_id = self._page_ids.get(opener) if opener is not None else None
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.PAGE_OPENED,
            page_id=page_id,
            parent_page_id=parent_page_id,
        )
        page.on("close", lambda: self._page_closed(identity_id, page))
        page.on("frameattached", lambda frame: self._frame_attached(identity_id, frame))
        page.on("framenavigated", lambda frame: self._frame_navigated(identity_id, frame))
        page.on("console", lambda message: self._console(identity_id, page, message))
        page.on("pageerror", lambda error: self._page_error(identity_id, page, error))
        page.on(
            "popup",
            lambda popup: self.register_page(
                identity_id,
                popup,
                parent_page=page,
            ),
        )

    def _link_popup(self, page: Page, parent_page: Page) -> None:
        page_id = self._page_ids.get(page)
        parent_page_id = self._page_ids.get(parent_page)
        if page_id is None or parent_page_id is None:
            return
        updated = []
        changed = False
        for event in self.events:
            if (
                event.kind is RecordingEventKind.PAGE_OPENED
                and event.page_id == page_id
                and event.parent_page_id is None
            ):
                event = event.model_copy(update={"parent_page_id": parent_page_id})
                changed = True
            updated.append(event)
        if changed:
            self.events = tuple(updated)
            self._payload_bytes = sum(self._event_size(event) for event in self.events)

    def check_runtime_budget(self, identity_id: str) -> None:
        if self.now_us() - self.started_at_us > self.budget.max_duration_us:
            self._stop_for_budget(identity_id, None)
            raise self.safety_error or JiejianError(
                ErrorCode.RECORD_EVENT_BUDGET,
                "浏览器录制超过运行时间预算",
            )

    def _route(
        self,
        identity_id: str,
        context: BrowserContext,
        route: Route,
    ) -> None:
        request = route.request
        page_id, frame_id, request_id = self._request_identity(identity_id, request)
        if len(self._request_ids) > self.scope.max_requests:
            self._stop_for_budget(identity_id, page_id)
            route.abort("blockedbyclient")
            return
        url, url_truncated = self._sanitizer.sanitize_url(request.url)
        headers, headers_truncated = self._sanitizer.sanitize_headers(request.headers)
        body, body_truncated = self._sanitizer.sanitize_body(
            request.post_data,
            request.headers.get("content-type", ""),
        )
        caused_by_action_id = self._take_pending_action(
            identity_id,
            page_id,
            frame_id,
            request.resource_type,
        )
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.REQUEST,
            page_id=page_id,
            frame_id=frame_id,
            request_id=request_id,
            caused_by_action_id=caused_by_action_id,
            url=url,
            method=request.method,
            resource_type=request.resource_type,
            headers=headers,
            body=body,
            truncated=url_truncated or headers_truncated or body_truncated,
        )
        if self.safety_error is not None:
            route.abort("blockedbyclient")
            return
        try:
            self._guards[identity_id].authorize_url(request.url)
        except JiejianError as exc:
            route.abort("blockedbyclient")
            self._stop_for_scope(
                identity_id,
                page_id=page_id,
                frame_id=frame_id,
                request_id=request_id,
                url=url,
                cause=exc.code,
            )
            return
        try:
            response = self._transport.fetch(
                request,
                context,
                self._guards[identity_id],
            )
        except JiejianError as exc:
            route.abort("blockedbyclient")
            if exc.code == ErrorCode.SCOPE_REDIRECT.value:
                self._stop_for_scope(
                    identity_id,
                    page_id=page_id,
                    frame_id=frame_id,
                    request_id=request_id,
                    url=url,
                    cause=exc.code,
                )
                return
            if exc.code == ErrorCode.RECORD_RESPONSE_UNSUPPORTED.value:
                self._stop_for_response(identity_id, page_id, request_id)
                return
            raise
        route.fulfill(
            status=response.status_code,
            headers=response.headers,
            body=response.body,
        )

    def _record_ui_action(
        self,
        identity_id: str,
        source: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> None:
        if set(payload) != {
            "kind",
            "element_locator",
            "field_name",
            "input_type",
        }:
            return
        raw_kind = payload.get("kind")
        kinds = {
            "click": RecordingEventKind.UI_CLICK,
            "input_change": RecordingEventKind.UI_INPUT_CHANGE,
            "submit": RecordingEventKind.UI_SUBMIT,
        }
        if raw_kind not in kinds:
            return
        page = source.get("page")
        frame = source.get("frame")
        if not isinstance(page, Page) or not isinstance(frame, Frame):
            return
        raw_locator = payload.get("element_locator")
        raw_field = payload.get("field_name")
        raw_input_type = payload.get("input_type")
        if not isinstance(raw_locator, str) or not raw_locator:
            return
        if raw_field is not None and not isinstance(raw_field, str):
            return
        if raw_input_type is not None and not isinstance(raw_input_type, str):
            return

        self.register_page(identity_id, page)
        page_id = self._page_ids[page]
        frame_id = self._frame_id(frame)
        locator, locator_truncated = self._sanitizer.sanitize_text(raw_locator)
        field_name, field_truncated = (
            self._sanitizer.sanitize_text(raw_field)
            if raw_field is not None
            else (None, False)
        )
        input_type, input_truncated = (
            self._sanitizer.sanitize_text(raw_input_type)
            if raw_input_type is not None
            else (None, False)
        )
        self._action_count += 1
        action_id = f"action_{self._action_count:06d}"
        self._append(
            identity_id=identity_id,
            kind=kinds[str(raw_kind)],
            page_id=page_id,
            frame_id=frame_id,
            action_id=action_id,
            element_locator=locator[:2_048],
            field_name=field_name[:256] if field_name is not None else None,
            input_type=input_type[:64] if input_type is not None else None,
            truncated=(
                locator_truncated
                or field_truncated
                or input_truncated
                or len(locator) > 2_048
                or (field_name is not None and len(field_name) > 256)
                or (input_type is not None and len(input_type) > 64)
            ),
        )
        if self.safety_error is None:
            self._pending_actions[(identity_id, page_id, frame_id)] = action_id

    def _take_pending_action(
        self,
        identity_id: str,
        page_id: str | None,
        frame_id: str | None,
        resource_type: str,
    ) -> str | None:
        if (
            page_id is None
            or frame_id is None
            or resource_type not in {"document", "fetch", "xhr"}
        ):
            return None
        return self._pending_actions.pop((identity_id, page_id, frame_id), None)

    def _websocket_route(self, identity_id: str, socket: WebSocketRoute) -> None:
        url, truncated = self._sanitizer.sanitize_url(socket.url)
        self._websocket_count += 1
        request_id = f"websocket_{self._websocket_count:06d}"
        try:
            self._guards[identity_id].authorize_url(self._http_url(socket.url))
        except JiejianError as exc:
            self._stop_for_scope(
                identity_id,
                request_id=request_id,
                url=url,
                cause=exc.code,
            )
            return
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.WEBSOCKET_OPENED,
            request_id=request_id,
            url=url,
            truncated=truncated,
        )
        if self.safety_error is not None:
            return
        server = socket.connect_to_server()
        socket.on_message(
            lambda message: self._websocket_message(
                identity_id,
                request_id,
                RecordingEventKind.WEBSOCKET_SENT,
                message,
                server.send,
            )
        )
        server.on_message(
            lambda message: self._websocket_message(
                identity_id,
                request_id,
                RecordingEventKind.WEBSOCKET_RECEIVED,
                message,
                socket.send,
            )
        )

    def _request_finished(self, identity_id: str, request: Request) -> None:
        if request in self._discarded_requests:
            # requestfinished 可能在开始采集后才到达；不能让准备期响应伪装成录制事件。
            self._discarded_requests.discard(request)
            return
        response = request.response()
        if response is None:
            return
        page_id, frame_id, request_id = self._request_identity(identity_id, request)
        headers, headers_truncated = self._sanitizer.sanitize_headers(response.headers)
        body, body_truncated = self._bounded_response_body(response)
        url, url_truncated = self._sanitizer.sanitize_url(response.url)
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.RESPONSE,
            page_id=page_id,
            frame_id=frame_id,
            request_id=request_id,
            url=url,
            status_code=response.status,
            headers=headers,
            body=body,
            truncated=headers_truncated or body_truncated or url_truncated,
        )

    def _bounded_response_body(self, response: Any) -> tuple[str | None, bool]:
        raw_length = response.headers.get("content-length")
        limit = min(self.budget.max_body_bytes, self.scope.max_response_bytes)
        try:
            length = int(raw_length) if raw_length is not None else None
        except ValueError:
            length = None
        if length is None or length < 0 or length > limit:
            return None, True
        try:
            raw_body = response.body()
        except PlaywrightError:
            return None, True
        if len(raw_body) > limit:
            return None, True
        return self._sanitizer.sanitize_body_bytes(
            raw_body,
            response.headers.get("content-type", ""),
        )

    def _request_identity(
        self,
        identity_id: str,
        request: Request,
    ) -> tuple[str | None, str | None, str]:
        request_id = self._request_ids.setdefault(
            request, f"request_{len(self._request_ids) + 1:06d}"
        )
        try:
            frame = request.frame
            page = frame.page
        except PlaywrightError:
            return None, None, request_id
        self.register_page(identity_id, page)
        return self._page_ids[page], self._frame_id(frame), request_id

    def _frame_id(self, frame: Frame) -> str:
        return self._frame_ids.setdefault(
            frame, f"frame_{len(self._frame_ids) + 1:06d}"
        )

    def _frame_attached(self, identity_id: str, frame: Frame) -> None:
        page = frame.page
        self.register_page(identity_id, page)
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.FRAME_ATTACHED,
            page_id=self._page_ids[page],
            frame_id=self._frame_id(frame),
        )

    def _frame_navigated(self, identity_id: str, frame: Frame) -> None:
        page = frame.page
        self.register_page(identity_id, page)
        url, truncated = self._sanitizer.sanitize_url(frame.url)
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.NAVIGATION,
            page_id=self._page_ids[page],
            frame_id=self._frame_id(frame),
            url=url,
            truncated=truncated,
        )

    def _page_closed(self, identity_id: str, page: Page) -> None:
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.PAGE_CLOSED,
            page_id=self._page_ids.get(page),
        )

    def _console(
        self,
        identity_id: str,
        page: Page,
        message: ConsoleMessage,
    ) -> None:
        text, truncated = self._sanitizer.sanitize_text(message.text)
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.CONSOLE,
            page_id=self._page_ids.get(page),
            message=text,
            truncated=truncated,
        )

    def _page_error(self, identity_id: str, page: Page, error: Error) -> None:
        message, truncated = self._sanitizer.sanitize_text(str(error))
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.PAGE_ERROR,
            page_id=self._page_ids.get(page),
            message=message,
            truncated=truncated,
        )

    def _web_error(self, identity_id: str, error: WebError) -> None:
        message, truncated = self._sanitizer.sanitize_text(str(error.error))
        self._append(
            identity_id=identity_id,
            kind=RecordingEventKind.PAGE_ERROR,
            message=message,
            truncated=truncated,
        )

    def _websocket_message(
        self,
        identity_id: str,
        request_id: str,
        kind: RecordingEventKind,
        message: str | bytes,
        forward: Callable[[str | bytes], None],
    ) -> None:
        if isinstance(message, bytes):
            body = f"[binary {min(len(message), self.budget.max_body_bytes)} bytes]"
            truncated = len(message) > self.budget.max_body_bytes
        else:
            body, truncated = self._sanitizer.sanitize_body(message, "text/plain")
        self._append(
            identity_id=identity_id,
            kind=kind,
            request_id=request_id,
            body=body,
            truncated=truncated,
        )
        if self.safety_error is None:
            forward(message)

    def _stop_for_scope(
        self,
        identity_id: str,
        *,
        page_id: str | None = None,
        frame_id: str | None = None,
        request_id: str | None = None,
        url: str | None = None,
        cause: str,
    ) -> None:
        if self.safety_error is not None:
            return
        self.safety_error = JiejianError(
            ErrorCode.RECORD_SCOPE_BLOCKED,
            "浏览器请求越出目标授权范围",
            details={"cause": cause},
        )
        self.safety_reason = RecordingReasonCode.TARGET_SCOPE_VIOLATION
        self._append(
            force_safety=True,
            identity_id=identity_id,
            kind=RecordingEventKind.SAFETY_BLOCKED,
            page_id=page_id,
            frame_id=frame_id,
            request_id=request_id,
            url=url,
            reason_code=ErrorCode.RECORD_SCOPE_BLOCKED.value,
        )

    def _stop_for_budget(self, identity_id: str, page_id: str | None) -> None:
        if self.safety_error is not None:
            return
        self.safety_error = JiejianError(
            ErrorCode.RECORD_EVENT_BUDGET,
            "浏览器录制超过事件、时间或体积预算",
        )
        self.safety_reason = RecordingReasonCode.EVENT_BUDGET_EXCEEDED
        self._append(
            force_safety=True,
            identity_id=identity_id,
            kind=RecordingEventKind.SAFETY_BLOCKED,
            page_id=page_id,
            reason_code=ErrorCode.RECORD_EVENT_BUDGET.value,
        )

    def _stop_for_response(
        self,
        identity_id: str,
        page_id: str | None,
        request_id: str,
    ) -> None:
        if self.safety_error is not None:
            return
        self.safety_error = JiejianError(
            ErrorCode.RECORD_RESPONSE_UNSUPPORTED,
            "浏览器响应不属于 有界普通 HTTP 能力范围",
        )
        self.safety_reason = RecordingReasonCode.UNSUPPORTED_RESPONSE
        self._append(
            force_safety=True,
            identity_id=identity_id,
            kind=RecordingEventKind.SAFETY_BLOCKED,
            page_id=page_id,
            request_id=request_id,
            reason_code=ErrorCode.RECORD_RESPONSE_UNSUPPORTED.value,
        )

    def _append(self, *, force_safety: bool = False, **values: Any) -> None:
        if self._frozen:
            return
        if not self._capture_enabled and not force_safety:
            return
        if not force_safety:
            if self.now_us() - self.started_at_us > self.budget.max_duration_us:
                self._stop_for_budget(str(values["identity_id"]), values.get("page_id"))
                return
            if len(self.events) >= max(0, self.budget.max_events - 1):
                self._stop_for_budget(str(values["identity_id"]), values.get("page_id"))
                return
        event = RecordingEvent(
            sequence=len(self.events) + 1,
            occurred_at_us=self.now_us(),
            **values,
        )
        size = self._event_size(event)
        if size > RECORDING_EVENT_MAX_BYTES:
            if not force_safety:
                self._stop_for_budget(str(values["identity_id"]), values.get("page_id"))
            return
        reserve = 0 if force_safety else _SAFETY_EVENT_RESERVE_BYTES
        if self._payload_bytes + size > self.budget.max_total_payload_bytes - reserve:
            if not force_safety:
                self._stop_for_budget(str(values["identity_id"]), values.get("page_id"))
            return
        self._payload_bytes += size
        self.events = (*self.events, event)

    @staticmethod
    def _event_size(event: RecordingEvent) -> int:
        return len(
            json.dumps(
                event.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )

    @staticmethod
    def _http_url(url: str) -> str:
        parsed = urlsplit(url)
        scheme = (
            "https"
            if parsed.scheme == "wss"
            else "http"
            if parsed.scheme == "ws"
            else parsed.scheme
        )
        return urlunsplit(
            (scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment)
        )
