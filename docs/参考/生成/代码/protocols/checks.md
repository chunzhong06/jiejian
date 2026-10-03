# 自动代码参考：protocols/checks

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/protocols/checks/__init__.py`

[打开源码](../../../../../product/protocols/checks/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/protocols/checks/check_publication.py`

[打开源码](../../../../../product/protocols/checks/check_publication.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckPublishedFile`
- `class CheckPublicationManifest`
- `CheckPublicationManifest.validate_files(self)`

静态import / dot-source：`product.protocols.checks.execution_request`、`pydantic`、`typing`

### `product/protocols/checks/check_result.py`

[打开源码](../../../../../product/protocols/checks/check_result.py) · Python AST；作用域内import不表示每次调用均执行。

- `CHECK_RESULT_MAX_BYTES`
- `check_request_marker(run_id, job_id, attempt, case_id) -> str`
- `class CheckAssetReference`
- `class CheckRunnerInput`
- `CheckRunnerInput.validate_assets(self)`
- `class CheckRunnerProgress`
- `CheckRunnerProgress.validate_counts(self)`
- `class CheckObservation`
- `CheckObservation.validate_window(self)`
- `class CheckCaseOutcome`
- `class CheckEvidence`
- `CheckEvidence.validate_associations(self)`
- `class CheckCaseResult`
- `class CheckPrimaryError`
- `class CheckRunnerResult`
- `CheckRunnerResult.validate_result(self)`
- `evidence_content_id(payload) -> str`
- `seal_check_evidence(**fields) -> CheckEvidence`
- `class ControlledCheckRunnerResult`
- `class NodeCheckRunnerResult`
- `class CheckResultProtocolError`
- `_CHECK_ROOTS`
- `canonical_check_document(document, known_secrets) -> bytes`
- `parse_check_document(raw, model, known_secrets) -> CheckDocument`

静态import / dot-source：`__future__`、`hashlib`、`json`、`product.backend.core.lifecycle`、`product.backend.core.verification.trace`、`product.protocols.checks.check_publication`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`pydantic`、`re`、`typing`

### `product/protocols/checks/check_runtime.py`

[打开源码](../../../../../product/protocols/checks/check_runtime.py) · Python AST；作用域内import不表示每次调用均执行。

- `CHECK_DOCUMENT_MAX_BYTES`
- `_SECRET`
- `class CheckBudget`
- `CheckBudget.validate_reserve(self)`
- `CheckBudget.fingerprint(self) -> str`
- `class CheckIdentityVerification`
- `CheckIdentityVerification.validate_read_only(self)`
- `class CheckIdentity`
- `CheckIdentity.validate_verification_actor(self)`
- `class CheckFlowStep`
- `class CheckAuxiliarySource`
- `CheckAuxiliarySource.validate_location(self)`
- `class CheckProofConfig`
- `CheckProofConfig.validate_source(self)`
- `class CheckRecoveryConfig`
- `CheckRecoveryConfig.validate_resource_binding(self)`
- `class CheckActionConfig`
- `CheckActionConfig.validate_flow(self)`
- `async_completion_candidates(action, observers, verified_identity_ids) -> dict[str, CheckAuxiliarySource]`
- `class CheckRuntimeBundle`
- `CheckRuntimeBundle.validate_references_and_limits(self)`
- `class ControlledCheckRuntimeBundle`
- `ControlledCheckRuntimeBundle.validate_runtime_source(self)`
- `class CheckRuntimeProtocolError`
- `class NodeCheckRuntimeBundle`
- `NodeCheckRuntimeBundle.validate_node_runtime(self)`
- `check_payload_contains_secret(value, known_secrets) -> bool`
- `canonical_check_runtime_bytes(bundle) -> bytes`
- `check_runtime_fingerprint(bundle) -> str`
- `parse_check_runtime(raw) -> CheckRuntimeBundle`

静态import / dot-source：`__future__`、`hashlib`、`json`、`product.protocols.checks.execution_request`、`product.protocols.observer`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`product.protocols.web.identity`、`product.protocols.web.request`、`product.protocols.web.response`、`product.protocols.web.target`、`pydantic`、`re`、`typing`、`作用域内：product.protocols.checks.json_check_runtime`

### `product/protocols/checks/execution_request.py`

[打开源码](../../../../../product/protocols/checks/execution_request.py) · Python AST；作用域内import不表示每次调用均执行。

- `RUNNER_INPUT_MAX_BYTES`
- `class WireModel`
- `WireModel.validate_resource_identifier(self)`
- `content_hash(domain, value) -> str`
- `class PermissionReference`
- `class FrozenPermission`
- `FrozenPermission.validate_semantics(self)`
- `class ExecutionAssetReference`
- `class RecordedProofReference`
- `class ObserverProofReference`
- `class EffectProofRequirement`
- `EffectProofRequirement.validate_proof(self)`
- `class RecoveryReference`
- `class CaseRole`
- `class ExecutionCase`
- `ExecutionCase.validate_case(self)`
- `class TwinInvariants`
- `class ExecutionTwin`
- `case_invariants(case)`
- `class ExecutionAction`
- `ExecutionAction.validate_twins(self)`
- `class ChangeContext`
- `ChangeContext.validate_sets(self)`
- `class RepairContext`
- `RepairContext.validate_sets(self)`
- `class PersistedExecutionRequestV3`
- `PersistedExecutionRequestV3.validate_project(self)`
- `class ExecutionV3Error`
- `canonical_execution_request_v3_bytes(request) -> bytes`
- `parse_execution_request_v3(raw) -> PersistedExecutionRequestV3`

静态import / dot-source：`__future__`、`enum`、`hashlib`、`json`、`pydantic`、`re`、`typing`

### `product/protocols/checks/json_check_runtime.py`

[打开源码](../../../../../product/protocols/checks/json_check_runtime.py) · Python AST；作用域内import不表示每次调用均执行。

- `class JsonCheckRuntimeBundle`
- `JsonCheckRuntimeBundle.source_coverage(self)`
- `class ManagedCheckRuntimeBundle`

静态import / dot-source：`product.protocols.checks.check_runtime`、`product.protocols.preparation.proof_sources`、`pydantic`、`typing`

<!-- GENERATED:END -->
