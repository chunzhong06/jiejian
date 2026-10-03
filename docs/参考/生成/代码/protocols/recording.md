# 自动代码参考：protocols/recording

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/protocols/recording/__init__.py`

[打开源码](../../../../../product/protocols/recording/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/protocols/recording/events.py`

[打开源码](../../../../../product/protocols/recording/events.py) · Python AST；作用域内import不表示每次调用均执行。

- `RECORDING_REQUEST_MAX_BYTES`
- `RECORDING_RESULT_MAX_BYTES`
- `RECORDING_EVENT_MAX_BYTES`
- `RECORDING_EVENT_MAX_COUNT`
- `_PAGE_ID`
- `_FRAME_ID`
- `_REQUEST_ID`
- `_ACTION_ID`
- `_REASON_CODE`
- `_SESSION_REF`
- `_HEADER_NAME`
- `_SENSITIVE_KEY`
- `_INLINE_SECRET`
- `class RecordingProtocolModel`
- `class RecordingRunnerResultType`
- `class RecordingCleanupStatus`
- `class RecordingEventKind`
- `class RecordingAuthMethod`
- `class RecordingBudget`
- `class RecordingCookieRef`
- `RecordingCookieRef.validate_cookie_metadata(self) -> RecordingCookieRef`
- `class RecordingSessionRef`
- `RecordingSessionRef.validate_auth_boundary(self) -> RecordingSessionRef`
- `class RecordingRunnerRequest`
- `RecordingRunnerRequest.validate_request_boundary(self) -> RecordingRunnerRequest`
- `required_recording_secret_names(request) -> tuple[str, ...]`
- `class RecordingHeader`
- `RecordingHeader.normalize_name(cls, value) -> str`
- `RecordingHeader.validate_redacted_header(self) -> RecordingHeader`
- `class RecordingEvent`
- `RecordingEvent.reject_url_userinfo(cls, value) -> str &#124; None`
- `RecordingEvent.reject_inline_secret_text(cls, value) -> str &#124; None`
- `RecordingEvent.validate_ui_action_boundary(self) -> RecordingEvent`
- `class RecordingRunnerError`
- `class RecordingRunnerResult`
- `RecordingRunnerResult.validate_reason_codes(cls, values) -> tuple[str, ...]`
- `RecordingRunnerResult.validate_result_matrix(self) -> RecordingRunnerResult`
- `canonical_recording_json_bytes(document, known_secrets) -> bytes`
- `parse_recording_request(raw, known_secrets) -> RecordingRunnerRequest`
- `parse_recording_result(raw, known_secrets) -> RecordingRunnerResult`
- `parse_recording_event(raw, known_secrets) -> RecordingEvent`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`json`、`math`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.recording.models`、`product.backend.core.redaction`、`product.protocols.web.target`、`pydantic`、`re`、`typing`、`urllib.parse`

### `product/protocols/recording/flow_draft.py`

[打开源码](../../../../../product/protocols/recording/flow_draft.py) · Python AST；作用域内import不表示每次调用均执行。

- `FLOW_DRAFT_MAX_BYTES`
- `FLOW_DRAFT_COMMAND_MAX_BYTES`
- `_ACTION_ID`
- `_REQUEST_ID`
- `_JSON_PATH`
- `_SENSITIVE_FIELD`
- `class FlowDraftProtocolModel`
- `class FlowDraftVariableStatus`
- `class FlowDraftVariableSource`
- `class FlowDraftVariable`
- `FlowDraftVariable.validate_source_state(self) -> FlowDraftVariable`
- `class FlowDraftResourceCandidate`
- `FlowDraftResourceCandidate.validate_resource_location(self) -> FlowDraftResourceCandidate`
- `class FlowDraftStep`
- `FlowDraftStep.validate_path(cls, value) -> str &#124; None`
- `FlowDraftStep.validate_step_boundary(self) -> FlowDraftStep`
- `class FlowDraft`
- `FlowDraft.validate_draft_graph(self) -> FlowDraft`
- `class ConfirmFlowDraftVariableChoice`
- `class ConfirmFlowDraftTarget`
- `class ConfirmFlowDraftResource`
- `_COMMAND_ADAPTER`
- `_COMMAND_TYPES`
- `flow_draft_source_choice_id(source) -> str`
- `canonical_flow_draft_json_bytes(document, known_secrets) -> bytes`
- `parse_flow_draft(raw, known_secrets) -> FlowDraft`
- `parse_flow_draft_review_command(raw, known_secrets) -> FlowDraftReviewCommand`
- `flow_draft_review_command_schema() -> dict[str, Any]`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`hashlib`、`json`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.recording.models`、`product.backend.core.redaction`、`product.protocols.web.workflow`、`pydantic`、`re`、`typing`、`urllib.parse`

### `product/protocols/recording/recording_flow.py`

[打开源码](../../../../../product/protocols/recording/recording_flow.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordingFlowModel`
- `class FlowVariableSource`
- `class FlowStep`
- `FlowStep.validate_metadata(self) -> FlowStep`
- `class Flow`
- `Flow.validate_dependency_graph(self) -> Flow`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.entities`、`product.backend.core.identifiers`、`product.protocols.web.workflow`、`pydantic`、`typing`

### `product/protocols/recording/recording_legacy.py`

[打开源码](../../../../../product/protocols/recording/recording_legacy.py) · Python AST；作用域内import不表示每次调用均执行。

- `class LegacyRecordingRunnerRequest`
- `LegacyRecordingRunnerRequest.subject_test_identity_id(self)`
- `LegacyRecordingRunnerRequest.resource_owner_test_identity_id(self)`
- `LegacyRecordingRunnerRequest.validate_request_boundary(self) -> LegacyRecordingRunnerRequest`
- `class LegacyFlowDraft`
- `LegacyFlowDraft.validate_draft_graph(self) -> LegacyFlowDraft`
- `class LegacyFlow`
- `LegacyFlow.validate_dependency_graph(self) -> LegacyFlow`
- `read_legacy_document(raw, kind, expected_hash)`

静态import / dot-source：`__future__`、`hashlib`、`json`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.recording.models`、`product.protocols.recording.events`、`product.protocols.recording.flow_draft`、`product.protocols.recording.recording_flow`、`product.protocols.web.workflow`、`pydantic`、`typing`、`作用域内：product.protocols.recording.events`、`作用域内：product.protocols.recording.flow_draft`、`作用域内：product.protocols.recording.recording_flow`

<!-- GENERATED:END -->
