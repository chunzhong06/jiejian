# 自动代码参考：backend/workflows/checks

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/checks/__init__.py`

[打开源码](../../../../../../product/backend/workflows/checks/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/checks/local_observer_wiring.py`

[打开源码](../../../../../../product/backend/workflows/checks/local_observer_wiring.py) · Python AST；作用域内import不表示每次调用均执行。

- `_MAX_DESCRIPTOR_BYTES`
- `_SECRET_REF`
- `_ID`
- `_AZURE_ACCOUNT`
- `class LocalObserverWiring`
- `load_local_observer_wiring(descriptor_path, var_dir, action_id, expected_origin, expected_resource_id, resource_mismatch_is_disabled) -> LocalObserverWiring &#124; None`

静态import / dot-source：`__future__`、`dataclasses`、`hashlib`、`json`、`pathlib`、`product.backend.core.errors`、`product.protocols`、`re`、`typing`、`urllib.parse`

### `product/backend/workflows/checks/reading/__init__.py`

[打开源码](../../../../../../product/backend/workflows/checks/reading/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/checks/reading/observation_reading.py`

[打开源码](../../../../../../product/backend/workflows/checks/reading/observation_reading.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ObservationReading`
- `observation_reading(item, source_type) -> ObservationReading`

静态import / dot-source：`__future__`、`product.protocols.checks.check_result`、`product.protocols.checks.execution_request`、`typing`

### `product/backend/workflows/checks/reading/results.py`

[打开源码](../../../../../../product/backend/workflows/checks/reading/results.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckRunView`
- `class CheckJobView`
- `class CheckProgressCaseView`
- `class CheckProgressView`
- `class CheckRunStatus`
- `class CheckHistoryCursor`
- `class CheckHistoryItem`
- `class CheckHistoryPage`
- `class CheckResultReader`
- `CheckResultReader.list_for_project(self, project_id) -> tuple[CheckRunStatus, ...]`
- `CheckResultReader.active_for_project(self, project_id) -> CheckRunStatus &#124; None`
- `CheckResultReader.history(self, project_id, limit, before_created_at_us, before_run_id, query, verdict, lifecycle) -> CheckHistoryPage`
- `CheckResultReader.status(self, run_id, project_id) -> CheckRunStatus`
- `CheckResultReader.package(self, run_id, project_id) -> CheckPackage`
- `CheckResultReader.evidence_index(self, run_id)`
- `CheckResultReader.evidence(self, run_id, evidence_id)`

静态import / dot-source：`__future__`、`hashlib`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.checks.check_packages`、`product.backend.infra.artifacts.checks.check_validation`、`product.backend.infra.runtime.jobs.requests.checks`、`product.backend.infra.runtime.paths`、`product.protocols.checks.check_result`、`product.protocols.checks.execution_request`、`pydantic`、`typing`

### `product/backend/workflows/checks/reading/story.py`

[打开源码](../../../../../../product/backend/workflows/checks/reading/story.py) · Python AST；作用域内import不表示每次调用均执行。

- `class StoryIdentity`
- `class StoryEffect`
- `class StoryControl`
- `class FactComparison`
- `class EvidenceExplanation`
- `class StoryTraceEvent`
- `class StoryExecutionPath`
- `class StoryProofCoverage`
- `class ActionResultStory`
- `class ResultStory`
- `class CheckStoryBuilder`
- `CheckStoryBuilder.bind_repairs(self, repairs)`
- `CheckStoryBuilder.validate_connections(self)`
- `CheckStoryBuilder.build(self, run_id, include_repair) -> ResultStory`

静态import / dot-source：`__future__`、`product.backend.core.checks.repair`、`product.backend.core.lifecycle`、`product.backend.core.verification.breakpoints`、`product.backend.core.verification.checks`、`product.backend.core.verification.trace`、`product.backend.workflows.checks.reading.observation_reading`、`product.backend.workflows.checks.reading.story_text`、`product.backend.workflows.checks.repairs.repair_presentation`、`product.protocols.checks.check_result`、`product.protocols.checks.execution_request`、`pydantic`、`typing`

### `product/backend/workflows/checks/reading/story_text.py`

[打开源码](../../../../../../product/backend/workflows/checks/reading/story_text.py) · Python AST；作用域内import不表示每次调用均执行。

- `JUDGEMENTS`
- `EXECUTION_LABELS`
- `EFFECT_LABELS`
- `PRECISION_LABELS`
- `CLAIM_BOUNDARIES`

### `product/backend/workflows/checks/registry.py`

[打开源码](../../../../../../product/backend/workflows/checks/registry.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RegisteredCheckIdentity`
- `class RegisteredResourceWindow`
- `class RegisteredAuxiliarySource`
- `RegisteredAuxiliarySource.validate_spec(self)`
- `class RegisteredCheckProof`
- `RegisteredCheckProof.validate_observer(self)`
- `class CheckRuntimeRegistration`
- `CheckRuntimeRegistration.validate_unique(self)`
- `CheckRuntimeRegistration.fingerprint(self)`
- `class CheckRuntimeRegistry`
- `CheckRuntimeRegistry.register(self, snapshot, expected_fingerprint)`
- `CheckRuntimeRegistry.bind_persistent_reader(self, reader)`
- `CheckRuntimeRegistry.validate_connections(self)`
- `CheckRuntimeRegistry.snapshot(self, project_id) -> CheckRuntimeRegistration &#124; None`
- `CheckRuntimeRegistry.unregister(self, project_id) -> None`
- `CheckRuntimeRegistry.proof(self, project_id, reference, effect_id)`
- `CheckRuntimeRegistry.contains(self, project_id, reference)`
- `CheckRuntimeRegistry.capability(self, project_id, reference, effect_id)`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.entities`、`product.backend.core.checks.plan`、`product.backend.core.errors`、`product.backend.core.preparation.bindings`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`product.protocols.observer`、`product.protocols.web.target`、`pydantic`、`threading`

### `product/backend/workflows/checks/repairs/__init__.py`

[打开源码](../../../../../../product/backend/workflows/checks/repairs/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/checks/repairs/repair.py`

[打开源码](../../../../../../product/backend/workflows/checks/repairs/repair.py) · Python AST；作用域内import不表示每次调用均执行。

- `build_current_repair_contract(package, source_case_id, breakpoint)`
- `class CurrentRepairService`
- `CurrentRepairService.contracts(self, run_id)`
- `CurrentRepairService.resolve(self, project_id, reference)`
- `CurrentRepairService.verification(self, run_id)`

静态import / dot-source：`__future__`、`product.backend.core.checks.repair`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.protocols.checks.execution_request`

### `product/backend/workflows/checks/repairs/repair_presentation.py`

[打开源码](../../../../../../product/backend/workflows/checks/repairs/repair_presentation.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RepairComparisonRow`
- `build_repair_comparison(contract, source, current) -> tuple[RepairComparisonRow, ...]`

静态import / dot-source：`__future__`、`product.backend.core.checks.repair`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.protocols.checks.execution_request`、`typing`

### `product/backend/workflows/checks/repairs/repair_text.py`

[打开源码](../../../../../../product/backend/workflows/checks/repairs/repair_text.py) · Python AST；作用域内import不表示每次调用均执行。

- `REPAIR_STATUS_LABELS`
- `CHANGE_IMPACT_LABELS`
- `REPAIR_REQUIREMENTS`
- `CURRENT_TASK_TEXT`

### `product/backend/workflows/checks/runtime_bundle.py`

[打开源码](../../../../../../product/backend/workflows/checks/runtime_bundle.py) · Python AST；作用域内import不表示每次调用均执行。

- `recorded_request_template(template) -> HttpRequestTemplate`
- `class CheckRuntimeBuilder`
- `CheckRuntimeBuilder.bind_runtime_readers(self, reference_reader, sources_reader)`
- `CheckRuntimeBuilder.validate_connections(self)`
- `CheckRuntimeBuilder.build(self, project_id, work)`
- `derive_target_classifiers(config, specs, identities)`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`product.backend.core.checks.plan`、`product.backend.core.errors`、`product.backend.core.preparation.bindings`、`product.backend.infra.artifacts.checks.check_packages`、`product.backend.infra.recording.request_store`、`product.backend.workflows.recording.lifecycle`、`product.backend.workflows.recording.source`、`product.protocols.checks.check_runtime`、`product.protocols.observer`、`product.protocols.recording.flow_draft`、`product.protocols.recording.recording_flow`、`product.protocols.runtime.node_runtime`、`product.protocols.web.request`、`product.protocols.web.response`、`typing`、`urllib.parse`、`作用域内：product.backend.workflows.runtime.ports`、`作用域内：product.protocols.checks.json_check_runtime`

### `product/backend/workflows/checks/service.py`

[打开源码](../../../../../../product/backend/workflows/checks/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckPreview`
- `class CheckService`
- `CheckService.set_revalidation_services(self, changes, repairs)`
- `CheckService.bind_delivery_recorder(self, recorder)`
- `CheckService.validate_connections(self)`
- `CheckService.pending_request(self, run_id)`
- `CheckService.cancel(self, project_id, run_id)`
- `CheckService.preview(self, project_id, change_id) -> CheckPreview`
- `CheckService.submit(self, project_id, expected_plan_fingerprint, idempotency_key, change_id)`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`logging`、`product.backend.core.checks.plan`、`product.backend.core.errors`、`product.backend.infra.artifacts.checks.check_validation`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.requests.checks`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`pydantic`、`threading`、`time`、`typing`、`uuid`、`作用域内：product.backend.core.checks.repair`、`作用域内：product.backend.infra.runtime.jobs.models`、`作用域内：product.backend.infra.storage`、`作用域内：product.backend.workflows.changes.observations`、`作用域内：product.backend.workflows.changes.service`、`作用域内：product.backend.workflows.checks.repairs.repair`

<!-- GENERATED:END -->
