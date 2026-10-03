# 自动代码参考：backend/infra/observers

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/observers/__init__.py`

[打开源码](../../../../../../product/backend/infra/observers/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/observers/adapters/__init__.py`

[打开源码](../../../../../../product/backend/infra/observers/adapters/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/observers/adapters/async_task.py`

[打开源码](../../../../../../product/backend/infra/observers/adapters/async_task.py) · Python AST；作用域内import不表示每次调用均执行。

- `ASYNC_TASK_PROCESS_ERROR`
- `ASYNC_TASK_UNAVAILABLE`
- `ASYNC_TASK_UNSUPPORTED`
- `ASYNC_TASK_HTTP_STATUS`
- `ASYNC_TASK_REDIRECT`
- `ASYNC_TASK_RESPONSE_INVALID`
- `ASYNC_TASK_RESPONSE_LIMIT`
- `ASYNC_TASK_CORRELATION_CONFLICT`
- `ASYNC_TASK_STATE_CONFLICT`
- `ASYNC_TASK_REQUEST_TIMEOUT`
- `ASYNC_TASK_OBSERVATION_TIMEOUT`
- `ASYNC_TASK_CANCELLED`
- `_PROCESS_REAP_TIMEOUT_SECONDS`
- `_SUPERVISION_SLICE_SECONDS`
- `_STATE_ORDER`
- `_RESPONSE_FIELDS`
- `class AsyncTaskObserverResult`
- `child_main(input_path, output_path) -> int`
- `run_async_task_observer(spec, correlation, phase, attempt_dir, parent_environ, python_executable) -> AsyncTaskObserverResult`
- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`dataclasses`、`hashlib`、`httpx`、`json`、`os`、`pathlib`、`product.backend.infra.execution.web.adapter`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.protocols.observer`、`product.protocols.web.target`、`subprocess`、`time`、`typing`、`urllib.parse`

### `product/backend/infra/observers/adapters/audit_log.py`

[打开源码](../../../../../../product/backend/infra/observers/adapters/audit_log.py) · Python AST；作用域内import不表示每次调用均执行。

- `AUDIT_OBSERVER_PROCESS_ERROR`
- `AUDIT_ROOT_MISSING`
- `AUDIT_ROOT_UNAVAILABLE`
- `AUDIT_TAG_NOT_FOUND`
- `AUDIT_EVENT_INVALID`
- `AUDIT_DUPLICATE_KEY`
- `AUDIT_EVENT_CONFLICT`
- `AUDIT_CHAIN_INVALID`
- `AUDIT_PARTIAL_LINE`
- `AUDIT_INVALID_UTF8`
- `AUDIT_BOM`
- `AUDIT_OFFSET_PAST_END`
- `AUDIT_FILE_CHANGED`
- `AUDIT_FILE_LIMIT`
- `AUDIT_LINE_LIMIT`
- `AUDIT_LINE_BYTES_LIMIT`
- `AUDIT_RECORD_LIMIT`
- `AUDIT_BYTE_LIMIT`
- `AUDIT_CURSOR_UNMATCHED`
- `AUDIT_CURSOR_AMBIGUOUS`
- `AUDIT_TIMEOUT`
- `_PROCESS_REAP_TIMEOUT_SECONDS`
- `_ROTATED_FILE`
- `_REPARSE_POINT`
- `_TRACE_AUDIT_FIELDS`
- `_TRACE_AUDIT_REQUIRED_FIELDS`
- `_TRACE_SCOPE_FIELDS`
- `_TRACE_ARRAY_FIELDS`
- `_TRACE_AUDIT_STRING_FIELDS`
- `_TRACE_AUDIT_TOKEN`
- `_TRACE_SEMANTIC_KEY`
- `_TRACE_KINDS`
- `_TRACE_INLINE_SECRET`
- `class AuditLogObserverResult`
- `child_main(input_path, output_path) -> int`
- `run_audit_log_observer(spec, correlation, phase, attempt_dir, parent_environ, python_executable, start_cursors) -> AuditLogObserverResult`
- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`ctypes`、`ctypes.wintypes`、`dataclasses`、`hashlib`、`json`、`msvcrt`、`os`、`pathlib`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.protocols.observer`、`re`、`stat`、`subprocess`、`time`、`typing`

### `product/backend/infra/observers/adapters/azure_blob.py`

[打开源码](../../../../../../product/backend/infra/observers/adapters/azure_blob.py) · Python AST；作用域内import不表示每次调用均执行。

- `AZURE_BLOB_ADAPTER_VERSION`
- `AZURE_BLOB_PROCESS_ERROR`
- `AZURE_BLOB_UNSUPPORTED`
- `AZURE_BLOB_SAS_INVALID`
- `AZURE_BLOB_UNAVAILABLE`
- `AZURE_BLOB_AUTH`
- `AZURE_BLOB_RESOURCE_MISSING`
- `AZURE_BLOB_THROTTLED`
- `AZURE_BLOB_HTTP_ERROR`
- `AZURE_BLOB_REDIRECT`
- `AZURE_BLOB_REQUEST_TIMEOUT`
- `AZURE_BLOB_OBSERVATION_TIMEOUT`
- `AZURE_BLOB_CANCELLED`
- `AZURE_BLOB_RESPONSE_LIMIT`
- `AZURE_BLOB_PAGE_LIMIT`
- `AZURE_BLOB_OBJECT_LIMIT`
- `AZURE_BLOB_OBJECT_BYTES`
- `AZURE_BLOB_PREFIX_VIOLATION`
- `AZURE_BLOB_RESPONSE_INVALID`
- `AZURE_BLOB_OBJECT_INVALID`
- `AZURE_BLOB_OBJECT_CONFLICT`
- `AZURE_BLOB_OBJECT_MISSING`
- `AZURE_BLOB_LENGTH_MISMATCH`
- `AZURE_BLOB_METADATA_INVALID`
- `AZURE_BLOB_CORRELATION_CONFLICT`
- `_ALLOWED_SAS_KEYS`
- `_REQUIRED_SAS_KEYS`
- `_SAS_CONTROL`
- `_TEXT_CONTROL`
- `_SECRET_MAX_BYTES`
- `_TEXT_MAX_BYTES`
- `_PROCESS_REAP_TIMEOUT_SECONDS`
- `_SUPERVISION_SLICE_SECONDS`
- `_MAX_MARKER_BYTES`
- `class BlobObserverResult`
- `child_main(input_path, output_path) -> int`
- `run_azure_blob_observer(spec, correlation, phase, attempt_dir, parent_environ, python_executable) -> BlobObserverResult`
- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`dataclasses`、`hashlib`、`httpx`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.protocols.observer`、`re`、`subprocess`、`time`、`typing`、`urllib.parse`、`xml.etree.ElementTree`

### `product/backend/infra/observers/adapters/azure_queue.py`

[打开源码](../../../../../../product/backend/infra/observers/adapters/azure_queue.py) · Python AST；作用域内import不表示每次调用均执行。

- `AZURE_QUEUE_ADAPTER_VERSION`
- `AZURE_QUEUE_PROCESS_ERROR`
- `AZURE_QUEUE_UNSUPPORTED`
- `AZURE_QUEUE_SAS_INVALID`
- `AZURE_QUEUE_UNAVAILABLE`
- `AZURE_QUEUE_AUTH`
- `AZURE_QUEUE_RESOURCE_MISSING`
- `AZURE_QUEUE_THROTTLED`
- `AZURE_QUEUE_HTTP_ERROR`
- `AZURE_QUEUE_REDIRECT`
- `AZURE_QUEUE_REQUEST_TIMEOUT`
- `AZURE_QUEUE_OBSERVATION_TIMEOUT`
- `AZURE_QUEUE_CANCELLED`
- `AZURE_QUEUE_RESPONSE_LIMIT`
- `AZURE_QUEUE_MESSAGE_LIMIT`
- `AZURE_QUEUE_MESSAGE_BYTES`
- `AZURE_QUEUE_RESPONSE_INVALID`
- `AZURE_QUEUE_MESSAGE_CONFLICT`
- `AZURE_QUEUE_CORRELATION_CONFLICT`
- `_ALLOWED_SAS_KEYS`
- `_REQUIRED_SAS_KEYS`
- `_SECRET_MAX_BYTES`
- `_TEXT_MAX_BYTES`
- `_SAS_CONTROL`
- `_PROCESS_REAP_TIMEOUT_SECONDS`
- `_SUPERVISION_SLICE_SECONDS`
- `_XML_CHUNK_BYTES`
- `class QueueObserverResult`
- `child_main(input_path, output_path) -> int`
- `run_azure_queue_observer(spec, correlation, phase, attempt_dir, parent_environ, python_executable) -> QueueObserverResult`
- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`base64`、`dataclasses`、`hashlib`、`httpx`、`json`、`math`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.protocols.observer`、`re`、`subprocess`、`time`、`typing`、`urllib.parse`、`xml.etree.ElementTree`

### `product/backend/infra/observers/adapters/json_source.py`

[打开源码](../../../../../../product/backend/infra/observers/adapters/json_source.py) · Python AST；作用域内import不表示每次调用均执行。

- `HISTORY_FIELDS`
- `INTEGER_FIELDS`
- `IDENTIFIER_FIELDS`
- `class SourceReadError`
- `strict_json(raw, limit)`
- `scalar(data, path, key)`
- `mapped_values(raw, config)`
- `preflight_source_checks(raw, config, resource_id, owner_subject_id, contract)`
- `class JsonHistoryFact`
- `project_history(before, after, operation_id, subject_id, resource_id, owner_id)`

静态import / dot-source：`__future__`、`dataclasses`、`json`、`math`、`product.protocols.preparation.proof_sources`、`re`

### `product/backend/infra/observers/adapters/owner_api.py`

[打开源码](../../../../../../product/backend/infra/observers/adapters/owner_api.py) · Python AST；作用域内import不表示每次调用均执行。

- `class OwnerApiObserverAdapter`
- `OwnerApiObserverAdapter.for_path(cls, path_template, timeout_us, max_bytes, utc_now_us) -> OwnerApiObserverAdapter`
- `OwnerApiObserverAdapter.observe(self, executor, resource_id, owner_token, case_id, phase, known_secrets, identity_runtime, request_marker) -> ObservationEnvelope`

静态import / dot-source：`__future__`、`dataclasses`、`product.backend.core.redaction`、`product.protocols.observer`、`typing`、`作用域内：product.backend.infra.execution.web.identity`

### `product/backend/infra/observers/adapters/sqlite.py`

[打开源码](../../../../../../product/backend/infra/observers/adapters/sqlite.py) · Python AST；作用域内import不表示每次调用均执行。

- `SQLITE_OBSERVER_PROCESS_ERROR`
- `SQLITE_QUERY_TIMEOUT`
- `SQLITE_SECRET_MISSING`
- `SQLITE_UNAVAILABLE`
- `SQLITE_QUERY_UNSUPPORTED`
- `SQLITE_QUERY_ERROR`
- `SQLITE_ROW_LIMIT`
- `SQLITE_BYTE_LIMIT`
- `_QUERY_TEMPLATE_ID`
- `_TABLE_OR_VIEW`
- `_QUERY`
- `_PROCESS_REAP_TIMEOUT_SECONDS`
- `class SqliteObserverResult`
- `child_main(input_path, output_path) -> int`
- `run_sqlite_observer(spec, correlation, phase, attempt_dir, parent_environ, python_executable) -> SqliteObserverResult`
- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`dataclasses`、`json`、`os`、`pathlib`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.protocols.observer`、`subprocess`、`time`、`typing`、`作用域内：sqlite3`、`作用域内：urllib.parse`

### `product/backend/infra/observers/checks/__init__.py`

[打开源码](../../../../../../product/backend/infra/observers/checks/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/observers/checks/check_disclosure.py`

[打开源码](../../../../../../product/backend/infra/observers/checks/check_disclosure.py) · Python AST；作用域内import不表示每次调用均执行。

- `protected_projection(value, fields, require_present)`
- `disclosure_proof(owner, response, fields, key, marker)`

静态import / dot-source：`collections.abc`、`hashlib`、`hmac`、`json`、`product.backend.core.verification.facts`

### `product/backend/infra/observers/checks/check_records.py`

[打开源码](../../../../../../product/backend/infra/observers/checks/check_records.py) · Python AST；作用域内import不表示每次调用均执行。

- `observe_records(owner, source, case, action_id, requirement, proof, phase, baseline_trusted, cleanup, common, source_identity)`

静态import / dot-source：`product.backend.infra.observers.adapters.json_source`、`product.backend.infra.observers.checks.check_disclosure`、`product.backend.infra.observers.records.record_facts`、`product.backend.infra.observers.records.record_source`、`product.backend.infra.observers.records.source_contracts`、`product.protocols.checks.check_result`、`product.protocols.preparation.proof_sources`、`product.protocols.web.request`、`作用域内：product.backend.infra.observers.checks.check_runtime`

### `product/backend/infra/observers/checks/check_runtime.py`

[打开源码](../../../../../../product/backend/infra/observers/checks/check_runtime.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckObservedSource`
- `class CheckObserverRuntime`
- `CheckObserverRuntime.restart_case_baseline(self, case_id) -> None`
- `CheckObserverRuntime.observe(self, case, action_id, requirement, proof, phase, baseline_trusted, cleanup) -> CheckObservedSource`
- `CheckObserverRuntime.trace(self, action, case)`

静态import / dot-source：`__future__`、`dataclasses`、`pathlib`、`product.backend.core.checks.plan`、`product.backend.core.errors`、`product.backend.infra.observers.adapters.owner_api`、`product.backend.infra.observers.coordinator`、`product.backend.infra.observers.effect_projector`、`product.protocols.checks.check_result`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`product.protocols.observer`、`secrets`、`time`、`作用域内：product.backend.infra.execution.web.check_runtime`、`作用域内：product.backend.infra.observers.checks.check_disclosure`、`作用域内：product.backend.infra.observers.checks.check_records`、`作用域内：product.backend.infra.observers.checks.check_trace`

### `product/backend/infra/observers/checks/check_trace.py`

[打开源码](../../../../../../product/backend/infra/observers/checks/check_trace.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_check_trace(case, action_id, planned_subject_id, marker, groups)`

静态import / dot-source：`json`、`product.backend.core.verification.trace`

### `product/backend/infra/observers/coordinator.py`

[打开源码](../../../../../../product/backend/infra/observers/coordinator.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ObserverCoordinator`
- `ObserverCoordinator.observe_one(self, session, binding, spec, correlation, phase, cursors) -> tuple[ObservationEnvelope &#124; None, ObserverOutcome, tuple[AuditLogStartCursor, ...]]`
- `ObserverCoordinator.observe_phase(self, session, case, phase, envelopes, outcomes, cursors, requirements_to_run, required_requirements) -> bool`
- `ObserverCoordinator.complete_required_outcomes(self, case, outcomes, requirements_to_run) -> tuple[ObserverOutcome, ...]`
- `default_observer_registry() -> ObserverRegistry`

静态import / dot-source：`__future__`、`collections.abc`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.observers.adapters.async_task`、`product.backend.infra.observers.adapters.audit_log`、`product.backend.infra.observers.adapters.azure_blob`、`product.backend.infra.observers.adapters.azure_queue`、`product.backend.infra.observers.adapters.sqlite`、`product.backend.infra.observers.registry`、`product.protocols`、`pydantic`、`typing`、`作用域内：product.backend.infra.execution.port`

### `product/backend/infra/observers/effect_projector.py`

[打开源码](../../../../../../product/backend/infra/observers/effect_projector.py) · Python AST；作用域内import不表示每次调用均执行。

- `_PHASE_ORDER`
- `_ABSENT_STATES`
- `class EffectProjection`
- `class EffectProjector`
- `EffectProjector.project_check(cls, case_id, resource_id, proof, spec, envelopes, disclosure_proof) -> ObservationFact`
- `EffectProjector.project(self, case_id, resource_id, effect, effect_binding, envelopes, baseline_integrity, disclosure_proof) -> EffectProjection`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`product.backend.core.boundaries.semantics`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions`、`product.protocols`、`product.protocols.checks.check_runtime`、`product.protocols.observer`、`typing`

### `product/backend/infra/observers/records/__init__.py`

[打开源码](../../../../../../product/backend/infra/observers/records/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/observers/records/record_facts.py`

[打开源码](../../../../../../product/backend/infra/observers/records/record_facts.py) · Python AST；作用域内import不表示每次调用均执行。

- `record_value(data, path)`
- `transaction_fact(before, view, path, expected_state, request_key, subject_id, resource_id, owner_id, collection)`
- `request_fact(before, view, path, expected_state, request_nonce, request_digest, subject_id, resource_id, owner_id, collection)`

静态import / dot-source：`__future__`、`product.backend.infra.observers.adapters.json_source`

### `product/backend/infra/observers/records/record_preflight.py`

[打开源码](../../../../../../product/backend/infra/observers/records/record_preflight.py) · Python AST；作用域内import不表示每次调用均执行。

- `managed_source_checks(view, config, resource_id, owner_subject_id, contract)`

静态import / dot-source：`product.backend.infra.observers.adapters.json_source`、`product.backend.infra.observers.records.record_facts`、`product.protocols.preparation.proof_sources`

### `product/backend/infra/observers/records/record_source.py`

[打开源码](../../../../../../product/backend/infra/observers/records/record_source.py) · Python AST；作用域内import不表示每次调用均执行。

- `record_provider(var_dir, runtime_reference, require_live) -> RecordProviderReference &#124; None`
- `read_record_source(var_dir, runtime_reference, config, resource_id, request_nonce, cancelled)`

静态import / dot-source：`__future__`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.execution.web.adapter`、`product.backend.infra.execution.web.identity`、`product.backend.infra.observers.adapters.json_source`、`product.backend.infra.runtime.process.controlled.artifact`、`product.backend.infra.runtime.process.controlled.node_owned`、`product.backend.infra.runtime.process.listeners`、`product.backend.infra.runtime.process.records.record_capabilities`、`product.backend.infra.runtime.process.records.record_server`、`product.backend.infra.runtime.process.tree`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.transaction_records`、`product.protocols.web.identity`、`product.protocols.web.request`、`product.protocols.web.target`、`urllib.parse`

### `product/backend/infra/observers/records/source_contracts.py`

[打开源码](../../../../../../product/backend/infra/observers/records/source_contracts.py) · Python AST；作用域内import不表示每次调用均执行。

- `audit_source_contract(var_dir, reference, config, require_live)`

静态import / dot-source：`__future__`、`hashlib`、`json`、`product.backend.infra.observers.records.record_source`、`product.protocols.preparation.proof_sources`

### `product/backend/infra/observers/records/transaction_store.py`

[打开源码](../../../../../../product/backend/infra/observers/records/transaction_store.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordStoreError`
- `class TransactionRecordStore`
- `TransactionRecordStore.close(self)`
- `TransactionRecordStore.seed(self, command) -> RecordSnapshot`
- `TransactionRecordStore.read(self, collection, resource_id) -> RecordSnapshot`
- `TransactionRecordStore.operation(self, operation_id) -> RecordOperation`
- `TransactionRecordStore.open_scope(self, request_nonce, request_digest) -> RecordRequestScope`
- `TransactionRecordStore.close_scope(self, scope_id, complete) -> RecordRequestScope`
- `TransactionRecordStore.proof_view(self, collection, resource_id, operation_id, request_nonce) -> RecordProofView`
- `TransactionRecordStore.transact(self, command) -> RecordOperation`

静态import / dot-source：`__future__`、`contextlib`、`hashlib`、`json`、`os`、`pathlib`、`product.protocols.runtime.transaction_records`、`sqlite3`、`struct`、`threading`、`uuid`、`作用域内：product.backend.infra.runtime.process.exclusive_file`

### `product/backend/infra/observers/registry.py`

[打开源码](../../../../../../product/backend/infra/observers/registry.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ObserverRegistry`
- `ObserverRegistry.register(self, observer_type, executor) -> None`
- `ObserverRegistry.get(self, observer_type) -> ObserverExecutor &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`product.protocols.observer`

<!-- GENERATED:END -->
