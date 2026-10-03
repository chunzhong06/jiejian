# 自动代码参考：backend/composition

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/composition/__init__.py`

[打开源码](../../../../../product/backend/composition/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.application`

### `product/backend/composition/application.py`

[打开源码](../../../../../product/backend/composition/application.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ApplicationCore`
- `ApplicationCore.close(self) -> None`
- `ApplicationCore.environment_for_secret_names(self, names) -> dict[str, str]`
- `ApplicationCore.worker_status(self) -> dict[str, object]`

静态import / dot-source：`__future__`、`collections.abc`、`functools`、`os`、`pathlib`、`product.backend`、`product.backend.core.errors`、`product.backend.infra.llm.adapters.httpx_transport`、`product.backend.infra.llm.profiles`、`product.backend.infra.recording.request_store`、`product.backend.infra.runtime.jobs.attempts`、`product.backend.infra.runtime.jobs.queue`、`product.backend.infra.runtime.jobs.targets`、`product.backend.infra.runtime.maintenance`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.worker.supervisor`、`product.backend.infra.secrets`、`product.backend.infra.storage`、`product.backend.workflows.application_understanding.service`、`product.backend.workflows.assistant.current_surfaces`、`product.backend.workflows.assistant.service`、`product.backend.workflows.business_boundaries`、`product.backend.workflows.business_boundaries.candidates.drafting`、`product.backend.workflows.business_boundaries.candidates.rule_candidates`、`product.backend.workflows.business_boundaries.reading.permissions`、`product.backend.workflows.checks.reading.results`、`product.backend.workflows.checks.reading.story`、`product.backend.workflows.checks.registry`、`product.backend.workflows.checks.runtime_bundle`、`product.backend.workflows.checks.service`、`product.backend.workflows.onboarding.workflow`、`product.backend.workflows.preparation.bindings.service`、`product.backend.workflows.preparation.materials.service`、`product.backend.workflows.preparation.service`、`product.backend.workflows.projects.catalog`、`product.backend.workflows.projects.lifecycle`、`product.backend.workflows.recording.credentials`、`product.backend.workflows.recording.lifecycle`、`product.backend.workflows.recording.project_submission`、`product.backend.workflows.recording.submission`、`product.backend.workflows.test_identities`、`product.backend.workflows.test_identities.execution`、`product.backend.workflows.test_identities.preparation`、`product.backend.workflows.workspace`、`time`、`typing`、`作用域内：product.backend.infra.runtime.process.controlled.node_locator`、`作用域内：product.backend.infra.runtime.session_secrets`、`作用域内：product.backend.infra.runtime.worker.runtime_supervisor`、`作用域内：product.backend.infra.samples`、`作用域内：product.backend.infra.storage`、`作用域内：product.backend.workflows.business_boundaries.reading.rule_details`、`作用域内：product.backend.workflows.changes`、`作用域内：product.backend.workflows.changes.identity`、`作用域内：product.backend.workflows.changes.observations`、`作用域内：product.backend.workflows.checks.repairs.repair`、`作用域内：product.backend.workflows.development`、`作用域内：product.backend.workflows.development.reading`、`作用域内：product.backend.workflows.examples.environment`、`作用域内：product.backend.workflows.examples.materials`、`作用域内：product.backend.workflows.preparation.bindings.sources`、`作用域内：product.backend.workflows.preparation.guidance.service`、`作用域内：product.backend.workflows.preparation.proofs.jobs`、`作用域内：product.backend.workflows.preparation.proofs.service`、`作用域内：product.backend.workflows.preparation.supplemental.service`、`作用域内：product.backend.workflows.projects.repair`、`作用域内：product.backend.workflows.runtime.activation`、`作用域内：product.backend.workflows.runtime.ports`、`作用域内：product.backend.workflows.runtime.setup`、`作用域内：product.backend.workflows.workspace.reading`

### `product/backend/composition/worker.py`

[打开源码](../../../../../product/backend/composition/worker.py) · Python AST；作用域内import不表示每次调用均执行。

- `class WorkerContainer`
- `WorkerContainer.close(self) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`functools`、`os`、`pathlib`、`product.backend.infra.recording.request_store`、`product.backend.infra.runtime.jobs.attempts`、`product.backend.infra.runtime.jobs.factory`、`product.backend.infra.runtime.jobs.queue`、`product.backend.infra.runtime.jobs.targets`、`product.backend.infra.runtime.paths`、`product.backend.infra.storage`、`product.backend.infra.storage.db`、`product.backend.workflows.preparation.proofs.jobs`、`product.backend.workflows.recording.lifecycle`、`product.backend.workflows.recording.submission`、`作用域内：product.backend.infra.runtime.jobs.target_handlers.runtime_load`、`作用域内：product.backend.infra.storage`、`作用域内：product.backend.workflows.runtime.load_jobs`

<!-- GENERATED:END -->
