# 自动代码参考：backend/infra/artifacts

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/artifacts/__init__.py`

[打开源码](../../../../../../product/backend/infra/artifacts/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.infra.artifacts.scans.scan_job`、`product.protocols.artifacts`

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

静态import / dot-source：`__future__`、`dataclasses`、`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.artifacts.checks.check_validation`、`product.backend.infra.runtime.paths`、`product.protocols.checks.check_publication`、`product.protocols.checks.check_result`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`re`、`stat`

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

### `product/backend/infra/artifacts/proof_reports.py`

[打开源码](../../../../../../product/backend/infra/artifacts/proof_reports.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProofReportStore`
- `ProofReportStore.save(self, report, known_secrets)`
- `ProofReportStore.read(self, digest)`

静态import / dot-source：`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.artifacts.checks.check_packages`、`product.protocols.preparation.proof_sources`、`re`

### `product/backend/infra/artifacts/reports/__init__.py`

[打开源码](../../../../../../product/backend/infra/artifacts/reports/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/artifacts/reports/report_reader.py`

[打开源码](../../../../../../product/backend/infra/artifacts/reports/report_reader.py) · Python AST；作用域内import不表示每次调用均执行。

- `_SAFE_ID`
- `_REPARSE_POINT`
- `class PublishedArtifactResult`
- `class ArtifactResultReader`
- `ArtifactResultReader.for_run(self, run_id, project_id) -> tuple[PublishedArtifactResult, ...]`

静态import / dot-source：`__future__`、`dataclasses`、`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`product.protocols.artifacts`、`re`、`stat`

### `product/backend/infra/artifacts/reports/report_store.py`

[打开源码](../../../../../../product/backend/infra/artifacts/reports/report_store.py) · Python AST；作用域内import不表示每次调用均执行。

- `_SAFE_ID`
- `_REPARSE_POINT`
- `_FORMATS`
- `_NAMES`
- `class ReportStore`
- `ReportStore.publish(self, report) -> ReportPackageManifest`
- `ReportStore.read(self, run_id, report_id) -> ReportDocument`
- `ReportStore.read_format(self, run_id, report_id, output_format) -> bytes`
- `ReportStore.list(self, run_id) -> list[dict[str, str]]`

静态import / dot-source：`__future__`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.reports.models`、`product.backend.infra.runtime.paths`、`product.protocols.report`、`re`、`shutil`、`stat`、`uuid`

### `product/backend/infra/artifacts/run_packages.py`

[打开源码](../../../../../../product/backend/infra/artifacts/run_packages.py) · Python AST；作用域内import不表示每次调用均执行。

- `PUBLICATION_MANIFEST_NAME`
- `_LEASE_OWNER_PATTERN`
- `_TERMINAL_PUBLISH_TYPES`
- `class AttemptPaths`
- `class StagedAttempt`
- `class TrustedResultReceipt`
- `class PublicationManifest`
- `PublicationManifest.validate_file_set(self) -> PublicationManifest`
- `class ValidatedPublication`
- `attempt_paths_for(var_dir, job) -> AttemptPaths`
- `final_run_dir(var_dir, project_id, run_id) -> Path`
- `validate_runner_staging(paths, job, known_secrets, require_receipt) -> tuple[RunnerResult, tuple[StagedArtifact, ...]]`
- `validate_published_run(final_dir, known_secrets) -> ValidatedPublication`
- `evidence_records_for_publication(final_dir, result, created_at_us, known_secrets) -> tuple[EvidenceIndexRecord, ...]`
- `read_publication_manifest(path) -> PublicationManifest`
- `write_publication_manifest(path, manifest) -> None`
- `reject_reparse_parents(root, target_parent) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.infra.runtime.paths`、`product.backend.infra.storage`、`product.protocols`、`pydantic`、`stat`、`typing`、`uuid`

### `product/backend/infra/artifacts/run_publication.py`

[打开源码](../../../../../../product/backend/infra/artifacts/run_publication.py) · Python AST；作用域内import不表示每次调用均执行。

- `_TERMINAL_PUBLISH_TYPES`
- `class RunPublisher`
- `RunPublisher.publish(self, staged, known_secrets) -> StagedAttempt`
- `RunPublisher.complete_existing(self, final_dir, known_secrets, require_active_lease) -> ValidatedPublication`
- `publication_manifest_sha256(manifest) -> str`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.run_packages`、`product.backend.infra.runtime.jobs.events`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.storage`、`product.protocols`、`time`

### `product/backend/infra/artifacts/scans/__init__.py`

[打开源码](../../../../../../product/backend/infra/artifacts/scans/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/artifacts/scans/artifact_ruleset.json`

[打开源码](../../../../../../product/backend/infra/artifacts/scans/artifact_ruleset.json) · 仅记录文件位置；配置值、样式规则和脚本执行关系不复制。


### `product/backend/infra/artifacts/scans/scan_job.py`

[打开源码](../../../../../../product/backend/infra/artifacts/scans/scan_job.py) · Python AST；作用域内import不表示每次调用均执行。

- `_JOB_ID`
- `class ArtifactCheckJobHandler`
- `ArtifactCheckJobHandler.run_job(self, job_id) -> ArtifactScanResult`

静态import / dot-source：`__future__`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.jobs.handlers`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.protocols.artifacts`、`re`、`subprocess`、`time`、`typing`、`uuid`、`作用域内：shutil`

### `product/backend/infra/artifacts/scans/scanner.py`

[打开源码](../../../../../../product/backend/infra/artifacts/scans/scanner.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ASSIGNMENT`
- `_PRIVATE_KEY`
- `_PREFIX_SECRET`
- `_FRONTEND_SECRET`
- `_SOURCE_MAPPING`
- `_FRONTEND_SUFFIXES`
- `_LOCK_NAMES`
- `class ArtifactScanFailure`
- `scan_artifact(request, clock) -> ArtifactScanResult`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.artifacts.run_packages`、`product.protocols.artifacts`、`re`、`stat`、`time`、`typing`

### `product/backend/infra/artifacts/scans/scanner_process.py`

[打开源码](../../../../../../product/backend/infra/artifacts/scans/scanner_process.py) · Python AST；作用域内import不表示每次调用均执行。

- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`json`、`pathlib`、`product.backend.infra.artifacts.scans.scanner`、`product.protocols.artifacts`

<!-- GENERATED:END -->
