# 自动代码参考：backend/workflows/reports

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/reports/__init__.py`

[打开源码](../../../../../../product/backend/workflows/reports/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.workflows.reports.presentation`

### `product/backend/workflows/reports/finalizer.py`

[打开源码](../../../../../../product/backend/workflows/reports/finalizer.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ResultFinalizer`
- `ResultFinalizer.status(self, run_id) -> RunFinalizationRecord`
- `ResultFinalizer.finalize(self, run_id) -> RunFinalizationRecord`
- `ResultFinalizer.reconcile(self) -> dict[str, int]`
- `ResultFinalizer.repair(self, run_id) -> RunFinalizationRecord`

静态import / dot-source：`__future__`、`collections.abc`、`contextlib`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.run_publication`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.lock`、`product.backend.infra.storage`、`product.backend.workflows.reports.findings`、`product.backend.workflows.reports.published`、`time`

### `product/backend/workflows/reports/findings.py`

[打开源码](../../../../../../product/backend/workflows/reports/findings.py) · Python AST；作用域内import不表示每次调用均执行。

- `_SEVERITY_ORDER`
- `class FindingMaterializer`
- `FindingMaterializer.materialize(self, view) -> str`
- `class FindingQueries`
- `FindingQueries.findings_for_run(self, run_id) -> list[dict[str, Any]]`
- `finding_inputs(reader, view) -> tuple[FindingInput, ...]`

静态import / dot-source：`__future__`、`collections`、`collections.abc`、`hashlib`、`json`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.findings`、`product.backend.infra.storage`、`product.backend.infra.storage.results.findings`、`product.backend.workflows.reports.published`、`product.protocols`、`time`、`typing`

### `product/backend/workflows/reports/gating.py`

[打开源码](../../../../../../product/backend/workflows/reports/gating.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RegressionGate`
- `RegressionGate.accept_baseline(self, run_id, actor, reason, expected_project_id) -> dict[str, Any]`
- `RegressionGate.get_baseline(self, baseline_id) -> dict[str, Any]`
- `RegressionGate.evaluate(self, baseline_id, run_id, policy) -> dict[str, Any]`
- `RegressionGate.get_gate_result(self, gate_result_id) -> dict[str, Any]`
- `RegressionGate.latest_gate_result(self, baseline_id, run_id) -> dict[str, Any]`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.behavior_differential`、`product.backend.core.verification.gating`、`product.backend.core.verification.permissions`、`product.backend.infra.storage.results.gating`、`product.backend.workflows.reports.findings`、`product.backend.workflows.reports.published`、`product.protocols`、`time`、`typing`

### `product/backend/workflows/reports/presentation/__init__.py`

[打开源码](../../../../../../product/backend/workflows/reports/presentation/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.core.verification.breakpoints`、`product.backend.workflows.reports.presentation.builder`、`product.backend.workflows.reports.presentation.explanations`、`product.backend.workflows.reports.presentation.models`

### `product/backend/workflows/reports/presentation/builder.py`

[打开源码](../../../../../../product/backend/workflows/reports/presentation/builder.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ResultPresentationBuilder`
- `ResultPresentationBuilder.build(self, run_id) -> ResultPresentation`
- `build_result_presentation(view, snapshot, finding_views, permission_policy, change_context) -> ResultPresentation`
- `_POLICY_RELATION_TEXT`
- `locate_published_breakpoints(snapshot, evidence_items, traces_by_case) -> dict[tuple[str, str], BreakpointResult]`
- `_WITNESS_LABELS`
- `_BREAKPOINT_LABELS`
- `_TRACE_KIND_LABELS`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.reports.repair`、`product.backend.core.verification.breakpoints`、`product.backend.core.verification.continuity`、`product.backend.core.verification.facts`、`product.backend.core.verification.trace`、`product.backend.workflows.reports.presentation.explanations`、`product.backend.workflows.reports.presentation.models`、`product.backend.workflows.reports.trace`、`product.protocols.observer`、`product.protocols.runner.execution_request`、`pydantic`、`typing`

### `product/backend/workflows/reports/presentation/explanations.py`

[打开源码](../../../../../../product/backend/workflows/reports/presentation/explanations.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ROLE_LABELS`
- `_ACTION_LABELS`
- `_RESOURCE_LABELS`
- `_RELATION_LABELS`
- `_SOURCE_PRESENTATION`
- `_SOURCE_STEPS`
- `_SOURCE_LIMITS`
- `_SOURCE_FOUND_FACTS`
- `_SOURCE_SUPPORTED_CLAIMS`

静态import / dot-source：`__future__`、`product.backend.core.lifecycle`、`product.backend.core.reports.repair`、`product.backend.core.verification.breakpoints`、`product.backend.core.verification.facts`、`product.backend.core.verification.trace`、`product.backend.workflows.reports.presentation.models`、`product.protocols.observer`、`product.protocols.runner.execution_request`、`typing`

### `product/backend/workflows/reports/presentation/models.py`

[打开源码](../../../../../../product/backend/workflows/reports/presentation/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PresentedCaseVerdict`
- `class ResultEvidenceSource`
- `class ResultWitnessItem`
- `class ResultConfirmedImpact`
- `class ResultDiagnosis`
- `ResultDiagnosis.validate_witness_order(self) -> ResultDiagnosis`
- `class ResultClaimBoundary`
- `class ResultEvidenceExplanation`
- `class ResultPresentationIssue`
- `class ResultRelevantIntent`
- `class ResultChangeVerification`
- `class ResultPresentation`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.lifecycle`、`product.backend.core.reports.repair`、`product.backend.core.verification.breakpoints`、`product.backend.core.verification.continuity`、`product.backend.core.verification.facts`、`product.backend.core.verification.trace`、`product.protocols.observer`、`pydantic`、`typing`

### `product/backend/workflows/reports/published.py`

[打开源码](../../../../../../product/backend/workflows/reports/published.py) · Python AST；作用域内import不表示每次调用均执行。

- `class PublishedRunView`
- `class PublishedResultReader`
- `PublishedResultReader.read(self, run_id) -> PublishedRunView`
- `PublishedResultReader.document(self, view, artifact_path) -> dict[str, Any]`
- `PublishedResultReader.execution_request(self, view) -> ExecutionRequestDocument`
- `PublishedResultReader.request_snapshot(self, view)`
- `PublishedResultReader.overview(self, run_id, published) -> dict[str, Any]`
- `PublishedResultReader.evidence_document(self, view, evidence_id) -> dict[str, Any]`
- `PublishedResultReader.evidence_detail(self, view, evidence_id) -> dict[str, Any]`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`hashlib`、`json`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.redaction`、`product.backend.infra.artifacts.run_packages`、`product.backend.infra.runtime.jobs.requests.execution`、`product.backend.infra.runtime.paths`、`product.backend.infra.storage`、`product.backend.workflows.assistant`、`product.protocols`、`product.protocols.runner.execution_request`、`typing`

### `product/backend/workflows/reports/repair.py`

[打开源码](../../../../../../product/backend/workflows/reports/repair.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RepairContractService`
- `RepairContractService.get(self, source_run_id, source_finding_id) -> RepairContract`
- `RepairContractService.for_run(self, source_run_id) -> RepairContract`
- `RepairContractService.verify_reference(self, project_id, reference) -> RepairContract`
- `RepairContractService.context(self, project_id, reference, permission_policy) -> RepairVerificationContext`
- `RepairContractService.requirement(self, source_run_id, source_finding_id) -> RepairRequirementView`
- `RepairContractService.verify_run(self, verification_run_id) -> RepairVerification &#124; None`

静态import / dot-source：`__future__`、`hashlib`、`json`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.reports.repair`、`product.backend.core.verification.continuity`、`product.backend.core.verification.differential`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions`、`product.backend.workflows.reports.presentation`、`product.backend.workflows.reports.trace`、`product.protocols.runner.execution_request`、`typing`

### `product/backend/workflows/reports/reporting.py`

[打开源码](../../../../../../product/backend/workflows/reports/reporting.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ReportBuilder`
- `ReportBuilder.generate_base(self, run_id) -> BaseRunReport`
- `ReportBuilder.generate_gate(self, run_id, gate_result_id) -> GateRunReport`
- `ReportBuilder.read(self, run_id, report_id) -> dict[str, Any]`
- `ReportBuilder.read_format(self, run_id, report_id, output_format) -> bytes`
- `ReportBuilder.list(self, run_id) -> list[dict[str, str]]`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.gating`、`product.backend.infra.artifacts.reports.report_reader`、`product.backend.infra.artifacts.reports.report_store`、`product.backend.infra.storage`、`product.backend.workflows.reports.published`、`product.protocols`、`product.protocols.report`、`typing`

### `product/backend/workflows/reports/trace.py`

[打开源码](../../../../../../product/backend/workflows/reports/trace.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_execution_traces(snapshot, evidence_items) -> tuple[ExecutionTrace, ...]`
- `build_execution_trace(snapshot, evidence) -> ExecutionTrace`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.verification.trace`、`product.protocols.observer`、`pydantic`、`typing`

<!-- GENERATED:END -->
