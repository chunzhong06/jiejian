# 自动代码参考：protocols/preparation

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/protocols/preparation/__init__.py`

[打开源码](../../../../../product/protocols/preparation/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/protocols/preparation/proof_artifacts.py`

[打开源码](../../../../../product/protocols/preparation/proof_artifacts.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProofArtifactInput`
- `ProofArtifactInput.complete_input(self)`

静态import / dot-source：`product.protocols.checks.business_facts`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`pydantic`、`typing`

### `product/protocols/preparation/proof_sources.py`

[打开源码](../../../../../product/protocols/preparation/proof_sources.py) · Python AST；作用域内import不表示每次调用均执行。

- `SAFE_SUBJECT`
- `safe_source_path(value)`
- `class SourceIdentityClaim`
- `class ProofSourceConfig`
- `ProofSourceConfig.path_template(cls, value)`
- `ProofSourceConfig.files(cls, values)`
- `ProofSourceConfig.bounded_mapping(self)`
- `safe_identity_path(value)`
- `class ManagedIdentityClaim`
- `ManagedIdentityClaim.request(cls, value)`
- `ManagedIdentityClaim.nonsensitive(cls, value)`
- `class ManagedProofSourceConfig`
- `ManagedProofSourceConfig.provider_mapping(self)`
- `source_identity_paths(config, identities)`
- `class LegacyProofSourceRevision`
- `LegacyProofSourceRevision.content_identity(self)`
- `class LegacySourceReadScope`
- `LegacySourceReadScope.loopback(cls, value)`
- `LegacySourceReadScope.paths(cls, values, info)`
- `class LegacyProofContractAttestation`
- `class LegacyProofPreflightInput`
- `LegacyProofPreflightInput.association(self)`
- `class ProofCheckItem`
- `class LegacyProofPreflightReport`
- `LegacyProofPreflightReport.usable_requires_all_checks(self)`
- `class FrozenJsonProofSource`
- `class ProofSourceAdoption`
- `class LegacyProofRunnerInput`
- `LegacyProofRunnerInput.input_hash(self)`
- `class AtomicProofSourceConfig`
- `AtomicProofSourceConfig.atomic_mapping(self)`
- `class FileProofSourceConfig`
- `FileProofSourceConfig.reference_pair(self)`
- `class ProofContractAttestation`
- `ProofContractAttestation.matching_profile(self)`
- `class ProofSourceRevision`
- `class SourceReadScope`
- `class ProofPreflightInput`
- `ProofPreflightInput.reference_ready(self)`
- `class ProofPreflightReport`
- `class FrozenProofSource`
- `FrozenProofSource.file_adoption_reference(self)`
- `class ProofRunnerInput`
- `read_source_revision(raw)`
- `read_source_scope(raw)`
- `read_preflight_input(raw)`
- `read_preflight_report(raw)`
- `read_proof_runner(raw)`
- `proof_bytes(value) -> bytes`
- `proof_fingerprint(value) -> str`

静态import / dot-source：`__future__`、`hashlib`、`json`、`product.protocols.checks.business_facts`、`product.protocols.checks.check_runtime`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`product.protocols.web.target`、`pydantic`、`re`、`typing`、`urllib.parse`

### `product/protocols/preparation/reference_capture.py`

[打开源码](../../../../../product/protocols/preparation/reference_capture.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CaptureActionConfig`
- `class CaptureRuntimeConfig`
- `CaptureRuntimeConfig.runtime_associations(self)`
- `class CaptureResourceSource`
- `class CaptureCase`
- `class CaptureRecoveryReference`
- `class ReferenceCaptureBaseline`
- `class ReferenceCapturePlan`
- `ReferenceCapturePlan.plan_identity(self)`
- `class ReferenceCaptureRequest`
- `ReferenceCaptureRequest.exact_project(self)`
- `class ReferenceCaptureRunnerInput`
- `ReferenceCaptureRunnerInput.exact_request(self)`
- `class ReferenceCaptureReport`
- `ReferenceCaptureReport.candidate_requires_facts(self)`

静态import / dot-source：`hashlib`、`json`、`product.protocols.checks.business_facts`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`product.protocols.preparation.proof_artifacts`、`product.protocols.preparation.proof_sources`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`product.protocols.web.target`、`pydantic`、`typing`

### `product/protocols/preparation/test_identity_preparation.py`

[打开源码](../../../../../product/protocols/preparation/test_identity_preparation.py) · Python AST；作用域内import不表示每次调用均执行。

- `IDENTITY_PREPARATION_REQUEST_MAX_BYTES`
- `IDENTITY_PREPARATION_RESULT_MAX_BYTES`
- `_PREPARATION_ID_PATTERN`
- `_SECRET_REF_PATTERN`
- `class IdentityPreparationResultType`
- `class IdentityPreparationRequest`
- `class PreparedCookieRef`
- `class IdentityPreparationResult`
- `IdentityPreparationResult.validate_result_matrix(self) -> IdentityPreparationResult`
- `canonical_identity_preparation_json_bytes(document) -> bytes`
- `parse_identity_preparation_request(raw) -> IdentityPreparationRequest`
- `parse_identity_preparation_result(raw) -> IdentityPreparationResult`

静态import / dot-source：`__future__`、`enum`、`json`、`product.backend.core.identifiers`、`product.backend.core.identities.models`、`product.protocols.runner.execution`、`product.protocols.web.target`、`pydantic`、`typing`

<!-- GENERATED:END -->
