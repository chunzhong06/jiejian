# 自动代码参考：protocols/_root

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/protocols/__init__.py`

[打开源码](../../../../../product/protocols/__init__.py) · Python AST；作用域内import不表示每次调用均执行。

- `_EXPORTS`

静态import / dot-source：`importlib`

### `product/protocols/artifacts.py`

[打开源码](../../../../../product/protocols/artifacts.py) · Python AST；作用域内import不表示每次调用均执行。

- `_SAFE_ID`
- `_RELATIVE_PATH`
- `RULESET_VERSION`
- `_ARTIFACT_ROOT_VERSIONS`
- `class ArtifactModel`
- `class ScanBudget`
- `class ArtifactCheckRequest`
- `ArtifactCheckRequest.absolute_path_only(cls, value) -> str`
- `class ArtifactScanStatus`
- `class ArtifactVerdict`
- `class ArtifactEvidence`
- `ArtifactEvidence.relative_path(cls, value) -> str`
- `class ArtifactFinding`
- `ArtifactFinding.validate_identity(self) -> ArtifactFinding`
- `class ArtifactScanResult`
- `ArtifactScanResult.validate_result(self) -> ArtifactScanResult`
- `class ArtifactResultFile`
- `class ArtifactResultManifest`
- `parse_artifact_check_request(raw) -> ArtifactCheckRequest`
- `parse_artifact_scan_result(raw) -> ArtifactScanResult`
- `parse_artifact_result_manifest(raw) -> ArtifactResultManifest`
- `stable_artifact_fingerprint(rule_id, path, line, kind) -> str`
- `stable_artifact_ids(artifact_id, rule_id, path, fingerprint) -> tuple[str, str]`

静态import / dot-source：`__future__`、`enum`、`hashlib`、`json`、`product.backend.core.identifiers`、`pydantic`、`re`、`typing`

### `product/protocols/report.py`

[打开源码](../../../../../product/protocols/report.py) · Python AST；作用域内import不表示每次调用均执行。

- `REPORT_SCHEMA_VERSION`
- `REPORT_PACKAGE_SCHEMA_VERSION`
- `REPORT_RULESET_VERSION`
- `_TOKEN`
- `_SHA256`
- `class ReportModel`
- `class ReportEvidenceRef`
- `class ReportFinding`
- `ReportFinding.validate_source_shape(self) -> ReportFinding`
- `class ReportObserverStatus`
- `ReportObserverStatus.validate_tokens(self) -> ReportObserverStatus`
- `class ReportRuntime`
- `ReportRuntime.validate_runtime_sources(self) -> ReportRuntime`
- `class ReportArtifact`
- `ReportArtifact.validate_artifact_sources(self) -> ReportArtifact`
- `class ArtifactSummaryStatus`
- `class ArtifactSummary`
- `ArtifactSummary.validate_summary(self) -> ArtifactSummary`
- `ArtifactSummary.create(cls, status, results, reason_codes) -> ArtifactSummary`
- `class ReportVersions`
- `ReportVersions.validate_versions(self) -> ReportVersions`
- `class ReportRun`
- `class ReportGate`
- `class ReportWitnessItem`
- `class ReportConfirmedImpact`
- `class ReportDiagnosis`
- `ReportDiagnosis.validate_diagnosis(self) -> ReportDiagnosis`
- `class ReportRepairReference`
- `class ReportRepairRequirement`
- `class ReportRepairVerification`
- `class ReportPresentationIssue`
- `ReportPresentationIssue.validate_evidence_refs(self) -> ReportPresentationIssue`
- `class ReportRelevantIntent`
- `class ReportPresentation`
- `ReportPresentation.validate_counts(self) -> ReportPresentation`
- `class BaseRunReport`
- `BaseRunReport.validate_base(self) -> BaseRunReport`
- `BaseRunReport.semantic_payload(self) -> dict[str, Any]`
- `BaseRunReport.create(cls, **values) -> BaseRunReport`
- `class GateRunReport`
- `GateRunReport.validate_gate(self) -> GateRunReport`
- `GateRunReport.semantic_payload(self) -> dict[str, Any]`
- `GateRunReport.create(cls, **values) -> GateRunReport`
- `_REPORT_ADAPTER`
- `class ReportPackageFile`
- `class ReportPackageManifest`
- `ReportPackageManifest.validate_manifest(self) -> ReportPackageManifest`
- `report_canonical_sha256(value) -> str`
- `artifact_summary_sha256(status, results, reason_codes) -> str`
- `base_semantic_input_sha256(run_id, publication_sha256, findings_snapshot_sha256, artifact_snapshot_sha256, versions) -> str`
- `gate_semantic_input_sha256(base_report_id, base_report_sha256, gate_result_id, gate_input_hash) -> str`
- `report_id_for(report_type, semantic_input_sha256) -> str`
- `parse_report_document(raw) -> ReportDocument`
- `parse_report_package_manifest(raw) -> ReportPackageManifest`
- `report_json_schema() -> dict[str, Any]`

静态import / dot-source：`__future__`、`enum`、`hashlib`、`json`、`product.backend.core.redaction`、`pydantic`、`re`、`typing`

### `product/protocols/schema.py`

[打开源码](../../../../../product/protocols/schema.py) · Python AST；作用域内import不表示每次调用均执行。

- `SCHEMA_ROOT`
- `class SchemaEntry`
- `SCHEMA_REGISTRY`
- `render_schema(entry) -> bytes`
- `synchronize_schemas(update, root) -> tuple[str, ...]`
- `main(argv) -> int`

静态import / dot-source：`__future__`、`argparse`、`dataclasses`、`importlib`、`json`、`pathlib`、`sys`、`typing`、`动态引用：未静态确定`

<!-- GENERATED:END -->
