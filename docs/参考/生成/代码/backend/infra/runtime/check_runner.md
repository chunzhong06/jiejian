# 自动代码参考：backend/infra/runtime/check_runner

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/runtime/check_runner/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/check_runner/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/runtime/check_runner/__main__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/check_runner/__main__.py) · Python AST；作用域内import不表示每次调用均执行。

- `main() -> int`

静态import / dot-source：`argparse`、`os`、`pathlib`、`product.backend.infra.runtime.check_runner.executor`

### `product/backend/infra/runtime/check_runner/executor.py`

[打开源码](../../../../../../../product/backend/infra/runtime/check_runner/executor.py) · Python AST；作用域内import不表示每次调用均执行。

- `execute_check_attempt(input_path, staging, environ) -> int`

静态import / dot-source：`__future__`、`logging`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.artifacts.checks.check_packages`、`product.backend.infra.execution.check_executor`、`product.backend.infra.execution.web.check_runtime`、`product.backend.infra.runtime.jobs.requests.checks`、`product.backend.infra.runtime.paths`、`product.protocols.checks.check_result`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`time`

### `product/backend/infra/runtime/check_runner/supervisor.py`

[打开源码](../../../../../../../product/backend/infra/runtime/check_runner/supervisor.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckRunnerSupervisor`
- `CheckRunnerSupervisor.run_job(self, job_id)`
- `class CheckJobHandler`

静态import / dot-source：`__future__`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.artifacts.checks.check_packages`、`product.backend.infra.artifacts.checks.check_publication`、`product.backend.infra.artifacts.checks.check_validation`、`product.backend.infra.execution.web.check_runtime`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.jobs.requests.checks`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.control`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.protocols.checks.check_result`、`product.protocols.checks.check_runtime`、`subprocess`、`time`

<!-- GENERATED:END -->
