# 自动代码参考：backend/core/recording

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/core/recording/__init__.py`

[打开源码](../../../../../../product/backend/core/recording/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/core/recording/models.py`

[打开源码](../../../../../../product/backend/core/recording/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `_REASON_CODE`
- `class RecordingState`
- `class RecordingPurpose`
- `class RecordingTerminalState`
- `class RecordingReasonCode`
- `class RecordingModel`
- `class RecordingStateEvent`
- `class Recording`
- `Recording.validate_lifecycle_times(self) -> Recording`
- `_TRANSITIONS`
- `transition_recording_state(recording, target, operator, occurred_at_us, reason_code, pending_terminal_state) -> Recording`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.identifiers`、`pydantic`、`re`、`typing`

### `product/backend/core/recording/sanitization.py`

[打开源码](../../../../../../product/backend/core/recording/sanitization.py) · Python AST；作用域内import不表示每次调用均执行。

- `_MAX_STRUCTURED_DEPTH`
- `_MAX_CAPTURED_HEADERS`
- `_MAX_CAPTURED_HEADER_VALUE_CHARS`
- `_SENSITIVE_FIELD`
- `class RecordingSanitizer`
- `RecordingSanitizer.sanitize_headers(self, headers) -> tuple[tuple[RecordingHeader, ...], bool]`
- `RecordingSanitizer.sanitize_url(self, value) -> tuple[str, bool]`
- `RecordingSanitizer.sanitize_body(self, value, content_type) -> tuple[str &#124; None, bool]`
- `RecordingSanitizer.sanitize_body_bytes(self, value, content_type, already_limited) -> tuple[str &#124; None, bool]`
- `RecordingSanitizer.sanitize_text(self, value) -> tuple[str, bool]`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`product.backend.core.redaction`、`product.protocols.recording.events`、`re`、`typing`、`urllib.parse`

<!-- GENERATED:END -->
