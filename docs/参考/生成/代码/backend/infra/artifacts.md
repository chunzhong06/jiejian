# 自动代码参考：backend/infra/artifacts

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/artifacts/__init__.py`

[打开源码](../../../../../../product/backend/infra/artifacts/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/artifacts/capture_baselines.py`

[打开源码](../../../../../../product/backend/infra/artifacts/capture_baselines.py) · Python AST；作用域内import不表示每次调用均执行。

- `save_capture_baseline(directory, value)`
- `read_capture_baseline(var_dir, work, project_id, capture_id)`

静态import / dot-source：`hashlib`、`os`、`product.backend.core.errors`、`product.backend.infra.artifacts.checks.check_packages`、`product.backend.infra.runtime.paths`、`product.protocols.preparation.proof_sources`、`product.protocols.preparation.reference_capture`

### `product/backend/infra/artifacts/capture_guard.py`

[打开源码](../../../../../../product/backend/infra/artifacts/capture_guard.py) · Python AST；作用域内import不表示每次调用均执行。

- `identity_source_fingerprint(identity)`
- `capture_inputs_current(work, request, var_dir)`

静态import / dot-source：`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`作用域内：product.backend.infra.artifacts.capture_baselines`

### `product/backend/infra/artifacts/checks/__init__.py`

[打开源码](../../../../../../product/backend/infra/artifacts/checks/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/artifacts/checks/check_packages.py`

[打开源码](../../../../../../product/backend/infra/artifacts/checks/check_packages.py) · Python AST；作用域内import不表示每次调用均执行。

- `MANIFEST_NAME`
- `MAX_FILE_BYTES`
- `MAX_FILES`
- `MAX_PACKAGE_BYTES`
- `class CheckPackage`
- `check_final_directory(var_dir, project_id, run_id) -> Path`
- `reject_check_links(root, path) -> None`
- `read_check_bytes(path, known_secrets) -> bytes`
- `validate_check_package(directory, published, known_secrets) -> CheckPackage`

静态import / dot-source：`__future__`、`dataclasses`、`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.artifacts.checks.check_validation`、`product.backend.infra.runtime.paths`、`product.protocols.checks.check_publication`、`product.protocols.checks.check_result`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`re`、`stat`、`作用域内：product.backend.infra.artifacts.checks.fact_validation`

### `product/backend/infra/artifacts/checks/check_publication.py`

[打开源码](../../../../../../product/backend/infra/artifacts/checks/check_publication.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckPublisher`
- `CheckPublisher.publish(self, staging, known_secrets) -> CheckPackage`
- `CheckPublisher.complete_existing(self, directory, known_secrets) -> CheckPackage`

静态import / dot-source：`__future__`、`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.checks.check_packages`、`product.backend.infra.artifacts.checks.check_validation`、`product.backend.infra.runtime.jobs.events`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.paths`、`product.backend.infra.storage.results.check_publications`、`product.backend.infra.storage.results.evidence`、`product.protocols.checks.check_publication`、`product.protocols.checks.check_result`、`time`

### `product/backend/infra/artifacts/checks/check_validation.py`

[打开源码](../../../../../../product/backend/infra/artifacts/checks/check_validation.py) · Python AST；作用域内import不表示每次调用均执行。

- `check_publication_budget_reason(actions, bundle) -> str &#124; None`
- `validate_check_inputs(request, bundle, runner_input) -> None`
- `validate_check_decisions(package) -> None`

静态import / dot-source：`__future__`、`hashlib`、`product.backend.core.errors`、`product.protocols.checks.check_result`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`作用域内：product.backend.core.verification.checks`

### `product/backend/infra/artifacts/checks/fact_validation.py`

[打开源码](../../../../../../product/backend/infra/artifacts/checks/fact_validation.py) · Python AST；作用域内import不表示每次调用均执行。

- `validate_frozen_facts(evidence, bundle, started_at_us, completed_at_us)`

静态import / dot-source：`product.backend.core.verification.business_facts`、`product.protocols.checks.business_facts`、`product.protocols.checks.check_result`、`product.protocols.preparation.proof_sources`

### `product/backend/infra/artifacts/legacy_run_reader.py`

[打开源码](../../../../../../product/backend/infra/artifacts/legacy_run_reader.py) · Python AST；作用域内import不表示每次调用均执行。

- `PUBLICATION_MANIFEST_NAME`
- `_LEASE_OWNER_PATTERN`
- `_TERMINAL_PUBLISH_TYPES`
- `class TrustedResultReceipt`
- `class PublicationManifest`
- `PublicationManifest.validate_file_set(self) -> PublicationManifest`
- `class ValidatedPublication`
- `final_run_dir(var_dir, project_id, run_id) -> Path`
- `validate_published_run(final_dir, known_secrets) -> ValidatedPublication`
- `read_publication_manifest(path) -> PublicationManifest`
- `reject_reparse_parents(root, target_parent) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.infra.runtime.paths`、`product.protocols`、`pydantic`、`stat`、`typing`

### `product/backend/infra/artifacts/proof_artifacts.py`

[打开源码](../../../../../../product/backend/infra/artifacts/proof_artifacts.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProofArtifactStore`
- `ProofArtifactStore.directory(self, project_id, asset_id)`
- `ProofArtifactStore.checked_bytes(raw, known_secrets)`
- `ProofArtifactStore.save(self, project_id, asset_id, raw, known_secrets)`
- `ProofArtifactStore.read(self, project_id, manifest, known_secrets)`
- `ProofArtifactStore.remove_unreferenced(self, project_id, asset_id)`
- `class CaptureReportStore`
- `CaptureReportStore.path(self, digest)`
- `CaptureReportStore.save(self, report, known_secrets)`
- `CaptureReportStore.read(self, digest)`
- `CaptureReportStore.publication_path(self, capture_id)`
- `CaptureReportStore.has_publication(self, capture_id)`
- `CaptureReportStore.seal_publication(self, report)`
- `CaptureReportStore.publication(self, capture_id)`

静态import / dot-source：`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.artifacts.checks.check_packages`、`product.protocols.checks.business_facts`、`product.protocols.preparation.proof_sources`、`product.protocols.preparation.reference_capture`、`re`、`uuid`

### `product/backend/infra/artifacts/proof_reports.py`

[打开源码](../../../../../../product/backend/infra/artifacts/proof_reports.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProofReportStore`
- `ProofReportStore.save(self, report, known_secrets)`
- `ProofReportStore.read(self, digest)`

静态import / dot-source：`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.artifacts.checks.check_packages`、`product.protocols.preparation.proof_sources`、`re`

### `product/backend/infra/artifacts/reports/__init__.py`

[打开源码](../../../../../../product/backend/infra/artifacts/reports/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/artifacts/run_packages.py`

[打开源码](../../../../../../product/backend/infra/artifacts/run_packages.py) · Python AST；作用域内import不表示每次调用均执行。

- `class AttemptPaths`
- `attempt_paths_for(var_dir, job) -> AttemptPaths`

静态import / dot-source：`dataclasses`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`product.backend.infra.storage`

### `product/backend/infra/artifacts/scans/__init__.py`

[打开源码](../../../../../../product/backend/infra/artifacts/scans/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/artifacts/scans/artifact_ruleset.json`

[打开源码](../../../../../../product/backend/infra/artifacts/scans/artifact_ruleset.json) · 仅记录文件位置；配置值、样式规则和脚本执行关系不复制。

<!-- GENERATED:END -->
