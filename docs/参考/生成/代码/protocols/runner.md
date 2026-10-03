# 自动代码参考：protocols/runner

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/protocols/runner/__init__.py`

[打开源码](../../../../../product/protocols/runner/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.codec`、`.evidence`、`.input`、`.result`

### `product/protocols/runner/codec.py`

[打开源码](../../../../../product/protocols/runner/codec.py) · Python AST；作用域内import不表示每次调用均执行。

- `canonical_runner_json_bytes(document, known_secrets) -> bytes`
- `canonical_runner_sha256(document, known_secrets) -> str`
- `parse_runner_input(raw, known_secrets) -> RunnerInput`
- `parse_runner_result(raw, known_secrets) -> RunnerResult`
- `parse_evidence(raw, known_secrets) -> Evidence`

静态import / dot-source：`.evidence`、`.input`、`.result`、`__future__`、`collections.abc`、`hashlib`、`json`、`product.backend.core.errors`、`pydantic`、`typing`

### `product/protocols/runner/evidence.py`

[打开源码](../../../../../product/protocols/runner/evidence.py) · Python AST；作用域内import不表示每次调用均执行。

- `class Evidence`
- `Evidence.validate_evidence(self) -> Evidence`
- `build_evidence(**fields) -> Evidence`

静态import / dot-source：`.input`、`__future__`、`collections.abc`、`enum`、`hashlib`、`json`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.core.verification.differential`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions.coverage`、`product.protocols.observer`、`product.protocols.runner.execution`、`pydantic`、`typing`

### `product/protocols/runner/execution.py`

[打开源码](../../../../../product/protocols/runner/execution.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProtocolModel`
- `class ExecutionBudget`
- `class SubjectExecutionBinding`
- `class ObserverRequirementKind`
- `class EffectClosurePolicy`
- `class EffectBinding`
- `EffectBinding.validate_effect_binding(self) -> EffectBinding`
- `class ObserverRequirementBinding`
- `ObserverRequirementBinding.validate_binding(self) -> ObserverRequirementBinding`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.identifiers`、`product.protocols.observer`、`pydantic`、`typing`

### `product/protocols/runner/execution_request.py`

[打开源码](../../../../../product/protocols/runner/execution_request.py) · Python AST；作用域内import不表示每次调用均执行。

- `_PROJECTION_PATH`
- `class ProtectedEffect`
- `ProtectedEffect.validate_text(cls, value) -> str`
- `ProtectedEffect.validate_fields(cls, values) -> tuple[str, ...]`
- `ProtectedEffect.validate_kind_fields(self) -> ProtectedEffect`
- `class PermissionPolicySnapshotEntry`
- `PermissionPolicySnapshotEntry.validate_semantic_projection(self) -> PermissionPolicySnapshotEntry`
- `PermissionPolicySnapshotEntry.fingerprint_payload(self) -> dict[str, Any]`
- `class PermissionPolicySnapshot`
- `PermissionPolicySnapshot.validate_snapshot(self) -> PermissionPolicySnapshot`
- `build_permission_policy_snapshot(project_id, policy_epoch, entries) -> PermissionPolicySnapshot`
- `class ChangeVerificationContext`
- `ChangeVerificationContext.validate_required_intents(self) -> ChangeVerificationContext`
- `class LegacyChangeVerificationContext`
- `LegacyChangeVerificationContext.validate_required_intents(self) -> LegacyChangeVerificationContext`
- `class RepairVerificationContext`
- `RepairVerificationContext.validate_context(self) -> RepairVerificationContext`
- `class PersistedExecutionRequest`
- `PersistedExecutionRequest.validate_budget_snapshot(self) -> PersistedExecutionRequest`
- `class LegacyPersistedExecutionRequest`
- `LegacyPersistedExecutionRequest.validate_budget_snapshot(self) -> LegacyPersistedExecutionRequest`
- `LegacyPersistedExecutionRequest.source_fingerprint(self) -> None`
- `canonical_execution_request_bytes(request, known_secrets) -> bytes`
- `canonical_legacy_execution_request_bytes(request, known_secrets) -> bytes`
- `parse_execution_request(raw, known_secrets) -> ExecutionRequestDocument`
- `required_secret_names(request) -> tuple[str, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`math`、`product.backend.core.boundaries.permissions`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.reports.repair`、`product.backend.core.verification.permissions`、`product.protocols.runner`、`product.protocols.runner.execution`、`product.protocols.web.profile`、`pydantic`、`re`、`typing`

### `product/protocols/runner/input.py`

[打开源码](../../../../../product/protocols/runner/input.py) · Python AST；作用域内import不表示每次调用均执行。

- `RUNNER_INPUT_MAX_BYTES`
- `RUNNER_RESULT_MAX_BYTES`
- `EVIDENCE_MAX_BYTES`
- `STAGED_ARTIFACT_MAX_BYTES`
- `STAGED_ARTIFACT_TOTAL_MAX_BYTES`
- `_LEASE_OWNER`
- `_REASON_CODE`
- `_HEX`
- `_TEXT`
- `_SECRET_KEY`
- `_SAFE_SECRET_KEY_NAMES`
- `_WINDOWS_DRIVE`
- `_FORBIDDEN_PATH_CHARS`
- `_WINDOWS_RESERVED_NAMES`
- `class RunnerResultType`
- `class CleanupStatus`
- `class RunnerFailurePhase`
- `class CleanupIssueCode`
- `class ResourceInjection`
- `class RunnerInput`
- `RunnerInput.validate_budget(self) -> RunnerInput`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.identifiers`、`product.protocols.runner.execution`、`product.protocols.web.profile`、`pydantic`、`re`、`typing`

### `product/protocols/runner/result.py`

[打开源码](../../../../../product/protocols/runner/result.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CleanupIssue`
- `class CleanupResult`
- `CleanupResult.validate_cleanup(self) -> CleanupResult`
- `class RunnerError`
- `class StagedArtifact`
- `StagedArtifact.validate_path(cls, value) -> str`
- `class RunnerResult`
- `RunnerResult.validate_result(self) -> RunnerResult`

静态import / dot-source：`.evidence`、`.input`、`__future__`、`collections.abc`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.protocols.runner.execution`、`pydantic`、`re`、`typing`

<!-- GENERATED:END -->
