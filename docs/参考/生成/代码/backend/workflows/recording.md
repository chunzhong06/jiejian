# 自动代码参考：backend/workflows/recording

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/recording/__init__.py`

[打开源码](../../../../../../product/backend/workflows/recording/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.credentials`

### `product/backend/workflows/recording/credentials.py`

[打开源码](../../../../../../product/backend/workflows/recording/credentials.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuntimeSecretVault`
- `RuntimeSecretVault.put(self, session_id, values) -> None`
- `RuntimeSecretVault.configured(self, session_id, names) -> tuple[bool, ...]`
- `RuntimeSecretVault.resolve(self, names) -> dict[str, str]`
- `RuntimeSecretVault.clear_session(self, session_id) -> None`
- `RuntimeSecretVault.clear(self) -> None`
- `RuntimeSecretVault.model_dump(self) -> dict[str, int]`
- `class RecordingCredentialProvider`
- `RecordingCredentialProvider.prepare(self, project_id, test_identity_id, recording_id, session_ref, now_us, expires_at_us) -> RecordingSessionRef`
- `RecordingCredentialProvider.clear(self, recording_id) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.identities.models`、`product.backend.infra.secrets`、`product.backend.workflows.test_identities`、`product.protocols`、`threading`

### `product/backend/workflows/recording/flow_compiler.py`

[打开源码](../../../../../../product/backend/workflows/recording/flow_compiler.py) · Python AST；作用域内import不表示每次调用均执行。

- `_SENSITIVE_FIELD`
- `class FlowDraftCompiler`
- `FlowDraftCompiler.compile(self, draft) -> Flow`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.protocols.recording.flow_draft`、`product.protocols.recording.recording_flow`、`product.protocols.web.workflow`、`pydantic`、`re`、`typing`、`urllib.parse`

### `product/backend/workflows/recording/lifecycle.py`

[打开源码](../../../../../../product/backend/workflows/recording/lifecycle.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordingStatusView`
- `class RecordingFinalizationView`
- `class RecordingLifecycle`
- `RecordingLifecycle.status(self, recording_id) -> RecordingStatusView`
- `RecordingLifecycle.start_capture(self, recording_id) -> RecordingStatusView`
- `RecordingLifecycle.discard_review(self, recording_id, now_us) -> RecordingStatusView`
- `RecordingLifecycle.stop_capture(self, recording_id) -> RecordingStatusView`
- `RecordingLifecycle.review(self, recording_id, command) -> RecordingStatusView`
- `RecordingLifecycle.finalize(self, recording_id, var_dir, now_us) -> RecordingFinalizationView`
- `RecordingLifecycle.finalize_if_unambiguous(self, recording_id, now_us)`
- `RecordingLifecycle.flow_path(var_dir, recording) -> Path`
- `RecordingLifecycle.load_final_flow(path, expected_hash) -> Flow`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.infra.artifacts.run_packages`、`product.backend.infra.recording.control`、`product.backend.infra.runtime.paths`、`product.backend.infra.storage`、`product.backend.workflows.recording.flow_compiler`、`product.backend.workflows.recording.review`、`product.protocols`、`product.protocols.recording.recording_flow`、`pydantic`、`typing`、`uuid`、`作用域内：product.backend.workflows.preparation.bindings.service`、`作用域内：product.backend.workflows.recording.source`、`作用域内：product.protocols.recording.flow_draft`、`作用域内：product.protocols.recording.recording_legacy`

### `product/backend/workflows/recording/processing.py`

[打开源码](../../../../../../product/backend/workflows/recording/processing.py) · Python AST；作用域内import不表示每次调用均执行。

- `_UI_KINDS`
- `_HTTP_METHODS`
- `_SENSITIVE_FIELD`
- `_OPAQUE_BUSINESS_VALUE`
- `class FlowDraftProcessor`
- `FlowDraftProcessor.build(self, recording_id, flow_id, business_action_id, action_revision, subject_test_identity_id, resource_owner_test_identity_id, events, purpose, parent_recording_id, effect_id, known_secrets, action_path_templates) -> FlowDraft`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`hashlib`、`json`、`product.backend.core.errors`、`product.backend.core.recording.models`、`product.backend.core.redaction`、`product.protocols.recording.events`、`product.protocols.recording.flow_draft`、`product.protocols.web.workflow`、`re`、`typing`、`urllib.parse`

### `product/backend/workflows/recording/project_submission.py`

[打开源码](../../../../../../product/backend/workflows/recording/project_submission.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProjectRecordingSubmission`
- `class ProjectRecordingService`
- `ProjectRecordingService.submit(self, project_id, business_action_id, action_revision, subject_test_identity_id, resource_owner_test_identity_id, subject_slot_id, resource_owner_slot_id, resource_owner_confirmed, duration_seconds, idempotency_key, purpose, parent_recording_id, effect_id, headless, material_candidate) -> ProjectRecordingSubmission`
- `ProjectRecordingService.submit_captured(self, project_id, events, **parameters) -> ProjectRecordingSubmission`

静态import / dot-source：`__future__`、`dataclasses`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.workflows.recording.source`、`product.backend.workflows.recording.submission`、`product.backend.workflows.test_identities`、`product.backend.workflows.test_identities.service`、`product.protocols`、`time`、`uuid`、`作用域内：product.backend.workflows.preparation.demonstrations`、`作用域内：product.backend.workflows.recording.source`

### `product/backend/workflows/recording/review.py`

[打开源码](../../../../../../product/backend/workflows/recording/review.py) · Python AST；作用域内import不表示每次调用均执行。

- `class FlowDraftReviewer`
- `FlowDraftReviewer.apply(self, draft, command) -> FlowDraft`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.protocols.recording.flow_draft`、`product.protocols.web.workflow`、`pydantic`、`re`、`typing`、`urllib.parse`

### `product/backend/workflows/recording/run_service.py`

[打开源码](../../../../../../product/backend/workflows/recording/run_service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordingRunService`
- `RecordingRunService.run(self, command, timeout_seconds, secret_names)`
- `RecordingRunService.capture(self, started, lifecycle, capture_control, timeout_seconds)`

静态import / dot-source：`__future__`、`collections.abc`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.jobs.dispatch`、`product.backend.infra.storage`、`product.backend.workflows.recording.submission`、`product.protocols`、`time`

### `product/backend/workflows/recording/source.py`

[打开源码](../../../../../../product/backend/workflows/recording/source.py) · Python AST；作用域内import不表示每次调用均执行。

- `identity_source_fingerprint(identity)`
- `current_recording_instance(work, project_id)`
- `recording_endpoint_fingerprint(understanding, controlled_instance_id)`
- `recording_source_fingerprint(action, identity, understanding, action_binding, actor_binding, owner, owner_actor_binding, controlled_instance_id)`
- `require_recording_source(work, request, historical_source, reused_source_fingerprint)`
- `require_persisted_recording_source(work, recording, var_dir, reused_source_fingerprint)`

静态import / dot-source：`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.recording.models`、`product.backend.workflows.business_boundaries.inspection`、`作用域内：product.backend.core.preparation.requirements`、`作用域内：product.backend.infra.recording.request_store`、`作用域内：product.backend.workflows.business_boundaries.reading.queries`、`作用域内：product.backend.workflows.preparation.demonstrations`、`作用域内：product.backend.workflows.preparation.service`、`作用域内：product.backend.workflows.test_identities.service`、`作用域内：product.protocols.recording.recording_legacy`、`作用域内：types`

### `product/backend/workflows/recording/submission.py`

[打开源码](../../../../../../product/backend/workflows/recording/submission.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RecordingApplicationModel`
- `class SubmitRecording`
- `class RecordingSubmissionResult`
- `class RecordingCompletionResult`
- `recording_target_scope(endpoint) -> WebTargetScope`
- `class RecordingSubmission`
- `RecordingSubmission.submit(self, command, known_secrets) -> RecordingSubmissionResult`
- `RecordingSubmission.captured_request_facts(request) -> dict`
- `RecordingSubmission.captured_existing(self, project_id, idempotency_key)`
- `RecordingSubmission.submit_captured(self, command, result, known_secrets) -> RecordingSubmissionResult`
- `RecordingSubmission.consume_result(self, job_id, lease_owner, fencing_token, result, now_us, known_secrets) -> RecordingCompletionResult`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.infra.recording.request_store`、`product.backend.infra.runtime.jobs.events`、`product.backend.infra.runtime.jobs.handlers`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.storage`、`product.backend.workflows.recording.processing`、`product.backend.workflows.recording.source`、`product.protocols`、`product.protocols.web.target`、`pydantic`、`time`、`typing`、`urllib.parse`、`uuid`

<!-- GENERATED:END -->
