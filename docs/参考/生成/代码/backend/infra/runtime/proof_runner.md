# 自动代码参考：backend/infra/runtime/proof_runner

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/runtime/proof_runner/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/proof_runner/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/runtime/proof_runner/__main__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/proof_runner/__main__.py) · Python AST；作用域内import不表示每次调用均执行。

- `main()`

静态import / dot-source：`argparse`、`functools`、`os`、`pathlib`、`product.backend.infra.artifacts.checks.check_packages`、`product.backend.infra.runtime.proof_runner.executor`、`product.backend.infra.storage`、`product.backend.infra.storage.db`、`product.protocols.preparation.proof_sources`、`作用域内：product.backend.infra.runtime.paths`

### `product/backend/infra/runtime/proof_runner/executor.py`

[打开源码](../../../../../../../product/backend/infra/runtime/proof_runner/executor.py) · Python AST；作用域内import不表示每次调用均执行。

- `execute_preflight(input, var_dir, uow_factory, environ, cancellation_requested)`

静态import / dot-source：`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.execution.web.adapter`、`product.backend.infra.execution.web.check_runtime`、`product.backend.infra.execution.web.identity`、`product.backend.infra.observers.adapters.json_source`、`product.backend.infra.observers.records.record_facts`、`product.backend.infra.observers.records.record_preflight`、`product.backend.infra.observers.records.record_source`、`product.backend.infra.observers.records.source_contracts`、`product.backend.infra.runtime.process.controlled.node_locator`、`product.backend.infra.runtime.process.controlled.node_owned`、`product.protocols.preparation.proof_sources`、`product.protocols.web.request`、`time`、`动态引用：os`

### `product/backend/infra/runtime/proof_runner/supervisor.py`

[打开源码](../../../../../../../product/backend/infra/runtime/proof_runner/supervisor.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProofPreflightHandler`
- `ProofPreflightHandler.run_job(self, job_id)`

静态import / dot-source：`os`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.checks.check_packages`、`product.backend.infra.execution.web.check_runtime`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.control`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.protocols.preparation.proof_sources`、`subprocess`、`time`

<!-- GENERATED:END -->
