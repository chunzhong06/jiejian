# 自动代码参考：protocols/observer

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/protocols/observer/__init__.py`

[打开源码](../../../../../product/protocols/observer/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.codec`、`.config`、`.invocation`、`.result`

### `product/protocols/observer/codec.py`

[打开源码](../../../../../product/protocols/observer/codec.py) · Python AST；作用域内import不表示每次调用均执行。

- `T`
- `canonical_json_bytes(value) -> bytes`
- `observer_canonical_sha256(value) -> str`
- `parse_observer_json(payload, model_type, known_secrets) -> T`

静态import / dot-source：`.config`、`.invocation`、`.result`、`__future__`、`hashlib`、`json`、`pydantic`、`typing`

### `product/protocols/observer/config.py`

[打开源码](../../../../../product/protocols/observer/config.py) · Python AST；作用域内import不表示每次调用均执行。

- `OBSERVER_JSON_MAX_BYTES`
- `OBSERVER_STATE_MAX_BYTES`
- `OBSERVER_STATE_MAX_DEPTH`
- `OBSERVER_STATE_MAX_KEYS`
- `_ID_PATTERN`
- `_TEXT_PATTERN`
- `_HEX_PATTERN`
- `_REASON_PATTERN`
- `_SECRET_REF_PATTERN`
- `_PATH_PATTERN`
- `class ObserverModel`
- `class ObserverType`
- `class ObservationPhase`
- `class ObservationCompleteness`
- `class CausalityStatus`
- `class ProvenanceType`
- `class ObserverOutcomeStatus`
- `class OwnerApiLocator`
- `OwnerApiLocator.validate_relative_path(cls, value) -> str`
- `class SqliteQueryLocator`
- `_AZURE_ACCOUNT_PATTERN`
- `_AZURE_QUEUE_NAME_PATTERN`
- `_AZURE_ALLOWED_QUEUE_FIELDS`
- `_AZURE_REQUIRED_QUEUE_FIELDS`
- `_AZURE_ALLOWED_METADATA_FIELDS`
- `_AZURE_REQUIRED_METADATA_FIELDS`
- `_AZURE_PREFIX_SEGMENT_PATTERN`
- `class QueuePeekBudget`
- `class AzureQueuePeekLocator`
- `AzureQueuePeekLocator.validate_service_url(cls, value, info) -> str`
- `AzureQueuePeekLocator.validate_queue_name(cls, value) -> str`
- `AzureQueuePeekLocator.validate_allowed_fields(cls, values) -> tuple[str, ...]`
- `class BlobObjectScanBudget`
- `class AzureBlobObjectLocator`
- `AzureBlobObjectLocator.validate_service_url(cls, value, info) -> str`
- `AzureBlobObjectLocator.validate_container_name(cls, value) -> str`
- `AzureBlobObjectLocator.validate_prefix_template(cls, value) -> str`
- `AzureBlobObjectLocator.validate_allowed_metadata_fields(cls, values) -> tuple[str, ...]`
- `_AUDIT_FIELD_PATTERN`
- `_AUDIT_FILENAME_PATTERN`
- `_AUDIT_OFFSET_FILENAME_PATTERN`
- `_AUDIT_ALLOWED_FIELDS`
- `_AUDIT_REQUIRED_FIELDS`
- `class AuditLogScanBudget`
- `class StructuredAuditLogLocator`
- `StructuredAuditLogLocator.validate_allowed_fields(cls, values) -> tuple[str, ...]`
- `_ASYNC_TASK_PATH_PATTERN`
- `class AsyncTaskStatus`
- `class AsyncTaskPollBudget`
- `class AsyncTaskApiLocator`
- `AsyncTaskApiLocator.validate_locator(self) -> AsyncTaskApiLocator`
- `class ObserverTarget`
- `class ObserverBudget`
- `class ObserverSpec`
- `ObserverSpec.validate_spec(self) -> ObserverSpec`

静态import / dot-source：`__future__`、`enum`、`ipaddress`、`pydantic`、`re`、`typing`、`urllib.parse`

### `product/protocols/observer/invocation.py`

[打开源码](../../../../../product/protocols/observer/invocation.py) · Python AST；作用域内import不表示每次调用均执行。

- `class Correlation`
- `class AuditLogStartCursor`
- `AuditLogStartCursor.validate_anchor(self) -> AuditLogStartCursor`
- `class ObserverInvocation`
- `ObserverInvocation.validate_invocation(self) -> ObserverInvocation`
- `class AsyncTaskObserverInvocation`
- `AsyncTaskObserverInvocation.validate_invocation(self) -> AsyncTaskObserverInvocation`
- `class AuditLogObserverInvocation`
- `AuditLogObserverInvocation.validate_invocation(self) -> AuditLogObserverInvocation`
- `class ObservationWindow`
- `ObservationWindow.validate_window(self) -> ObservationWindow`

静态import / dot-source：`.config`、`__future__`、`pydantic`、`re`、`typing`

### `product/protocols/observer/result.py`

[打开源码](../../../../../product/protocols/observer/result.py) · Python AST；作用域内import不表示每次调用均执行。

- `class NormalizedState`
- `NormalizedState.validate_hash(self) -> NormalizedState`
- `build_normalized_state(payload, known_secrets) -> NormalizedState`
- `class ObservationProvenance`
- `ObservationProvenance.validate_provenance(self) -> ObservationProvenance`
- `class ObservationEnvelope`
- `ObservationEnvelope.normalize_reasons(cls, values) -> tuple[str, ...]`
- `ObservationEnvelope.validate_envelope(self) -> ObservationEnvelope`
- `class ObserverOutcome`
- `evaluate_observer_outcome(envelope, required, adapter_error) -> ObserverOutcome`

静态import / dot-source：`.config`、`.invocation`、`__future__`、`collections.abc`、`hashlib`、`json`、`math`、`pydantic`、`re`、`typing`

<!-- GENERATED:END -->
