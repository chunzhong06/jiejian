# 自动代码参考：backend/infra/recording

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/recording/__init__.py`

[打开源码](../../../../../../product/backend/infra/recording/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/recording/browser.py`

[打开源码](../../../../../../product/backend/infra/recording/browser.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordingPage`
- `RecordingPage.url(self) -> str`
- `RecordingPage.is_closed(self) -> bool`
- `RecordingPage.goto(self, url, wait_until, timeout_ms) -> None`
- `RecordingPage.click(self, selector, timeout_ms) -> None`
- `RecordingPage.fill(self, selector, value, timeout_ms) -> None`
- `RecordingPage.evaluate(self, expression, argument) -> Any`
- `RecordingPage.wait_for_timeout(self, milliseconds) -> None`
- `RecordingPage.close(self) -> None`
- `class RecordingBrowserSession`
- `RecordingBrowserSession.identity_ids(self) -> tuple[str, ...]`
- `RecordingBrowserSession.new_page(self, identity_id) -> RecordingPage`
- `RecordingBrowserSession.capture_started(self) -> bool`
- `RecordingBrowserSession.wait_for_capture_start(self, page, identity_id) -> bool`
- `RecordingBrowserSession.stop_requested(self) -> bool`
- `class BrowserRecordingAdapter`
- `BrowserRecordingAdapter.run(self, request, interaction, known_secrets, secret_values, cancellation_requested, now_us, capture_controlled, ready_callback, start_requested, started_callback, stop_requested, monotonic) -> RecordingRunnerResult`

静态import / dot-source：`__future__`、`collections.abc`、`playwright.sync_api`、`product.backend.core.errors`、`product.backend.core.recording.models`、`product.backend.infra.recording.events`、`product.protocols.recording.events`、`time`、`typing`

### `product/backend/infra/recording/control.py`

[打开源码](../../../../../../product/backend/infra/recording/control.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordingControlPaths`
- `control_paths_for_attempt(attempt_dir) -> RecordingControlPaths`
- `write_control_marker(path, attempt_dir) -> bool`
- `valid_control_marker(path) -> bool`

静态import / dot-source：`__future__`、`dataclasses`、`os`、`pathlib`、`product.backend.core.errors`、`uuid`

### `product/backend/infra/recording/events.py`

[打开源码](../../../../../../product/backend/infra/recording/events.py) · Python AST；作用域内import不表示每次调用均执行。

- `_SAFETY_EVENT_RESERVE_BYTES`
- `class RecordingEventCollector`
- `RecordingEventCollector.begin_capture(self) -> None`
- `RecordingEventCollector.freeze(self) -> None`
- `RecordingEventCollector.attach_context(self, identity_id, context) -> None`
- `RecordingEventCollector.register_page(self, identity_id, page, parent_page) -> None`
- `RecordingEventCollector.check_runtime_budget(self, identity_id) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`playwright.sync_api`、`product.backend.core.errors`、`product.backend.core.recording.models`、`product.backend.core.recording.sanitization`、`product.backend.infra.execution.web.adapter`、`product.backend.infra.recording.transport`、`product.backend.infra.recording.ui_capture`、`product.protocols.recording.events`、`product.protocols.web.target`、`typing`、`urllib.parse`

### `product/backend/infra/recording/process.py`

[打开源码](../../../../../../product/backend/infra/recording/process.py) · Python AST；作用域内import不表示每次调用均执行。

- `RECORDING_RUNNER_EXIT_OK`
- `RECORDING_RUNNER_EXIT_PROTOCOL`
- `RECORDING_RUNNER_EXIT_INTERNAL`
- `_CANCEL_PATH_ENV`
- `_ATTEMPT_DIR_ENV`
- `execute_recording_runner(stdin, stdout, stderr, environ, adapter, monotonic) -> int`
- `main() -> int`

静态import / dot-source：`__future__`、`collections.abc`、`logging`、`os`、`pathlib`、`playwright.sync_api`、`product.backend.core.errors`、`product.backend.infra.recording.browser`、`product.backend.infra.recording.control`、`product.protocols`、`sys`、`time`、`typing`

### `product/backend/infra/recording/request_store.py`

[打开源码](../../../../../../product/backend/infra/recording/request_store.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordingRequestStore`
- `RecordingRequestStore.write(self, job_id, request, known_secrets) -> tuple[str, bool]`
- `RecordingRequestStore.load(self, job_id, expected_hash, known_secrets) -> RecordingRunnerRequest`
- `RecordingRequestStore.remove_if_matches(self, job_id, request_hash) -> None`
- `RecordingRequestStore.load_history(self, job_id, expected_hash)`
- `RecordingRequestStore.path_for(self, job_id) -> Path`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`hmac`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.infra.runtime.paths`、`product.protocols`、`re`、`uuid`、`作用域内：json`、`作用域内：product.protocols.recording.recording_legacy`

### `product/backend/infra/recording/transport.py`

[打开源码](../../../../../../product/backend/infra/recording/transport.py) · Python AST；作用域内import不表示每次调用均执行。

- `_HOP_BY_HOP_HEADERS`
- `class BoundedHTTPResponse`
- `class BoundedRouteTransport`
- `BoundedRouteTransport.fetch(self, request, context, guard) -> BoundedHTTPResponse`

静态import / dot-source：`__future__`、`dataclasses`、`httpx`、`playwright.sync_api`、`product.backend.core.errors`、`product.backend.infra.execution.web.adapter`、`product.protocols.web.target`、`typing`

### `product/backend/infra/recording/ui_capture.py`

[打开源码](../../../../../../product/backend/infra/recording/ui_capture.py) · Python AST；作用域内import不表示每次调用均执行。

- `_BINDING_NAME`
- `_INIT_SCRIPT`
- `install_ui_capture(context, callback) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`playwright.sync_api`、`typing`

<!-- GENERATED:END -->
