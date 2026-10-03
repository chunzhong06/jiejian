# 自动代码参考：backend/infra/runtime/process

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/runtime/process/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/__init__.py) · Python AST；作用域内import不表示每次调用均执行。

- `_EXPORTS`

静态import / dot-source：`importlib`、`动态引用：未静态确定`

### `product/backend/infra/runtime/process/control.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/control.py) · Python AST；作用域内import不表示每次调用均执行。

- `DEFAULT_LEASE_DURATION_US`
- `DEFAULT_POLL_INTERVAL_SECONDS`
- `DEFAULT_TERMINATION_GRACE_SECONDS`
- `force_terminate_process_tree(process, timeout) -> None`
- `class AttemptProcessControl`
- `AttemptProcessControl.termination_grace_seconds(self) -> float`
- `AttemptProcessControl.monitor(self, process, job, max_duration_us, cancel_path) -> tuple[bool, bool]`
- `AttemptProcessControl.renew(self, job) -> None`
- `AttemptProcessControl.read_job(self, job_id) -> JobRecord`

静态import / dot-source：`__future__`、`collections.abc`、`logging`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.infra.runtime.jobs.handlers`、`product.backend.infra.runtime.jobs.models`、`product.backend.infra.runtime.process.tree`、`product.backend.infra.storage`、`subprocess`、`time`、`typing`

### `product/backend/infra/runtime/process/controlled/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/controlled/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/runtime/process/controlled/artifact.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/controlled/artifact.py) · Python AST；作用域内import不表示每次调用均执行。

- `inspect_runtime_files(source_root, files) -> tuple[RuntimeFile, ...]`
- `create_runtime_artifact(source_root, artifact_store, files, entry_module, interpreter_fingerprint, dependency_files) -> tuple[Path, RuntimeLaunchManifest]`
- `create_node_runtime_artifact(source_root, artifact_store, manifest) -> Path`
- `verify_runtime_artifact(source_root, manifest) -> None`
- `read_runtime_manifest(path) -> RuntimeLaunchManifest`
- `python_runtime_files(source_root) -> tuple[RuntimeFile, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`pathlib`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`uuid`、`作用域内：os`

### `product/backend/infra/runtime/process/controlled/bootstrap.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/controlled/bootstrap.py) · Python AST；作用域内import不表示每次调用均执行。

- `_GATE_TIMEOUT_SECONDS`
- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`pathlib`、`runpy`、`sys`、`time`、`作用域内：product.backend.infra.runtime.process.controlled.identity`

### `product/backend/infra/runtime/process/controlled/correspondence.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/controlled/correspondence.py) · Python AST；作用域内import不表示每次调用均执行。

- `runtime_artifact_store(var_dir) -> Path`
- `runtime_corresponds(var_dir, reference) -> bool`

静态import / dot-source：`pathlib`、`product.backend.infra.runtime.process.controlled.artifact`、`product.backend.infra.runtime.process.tree`、`product.protocols.runtime.runtime_identity`

### `product/backend/infra/runtime/process/controlled/identity.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/controlled/identity.py) · Python AST；作用域内import不表示每次调用均执行。

- `SUPPORTED_PYTHON`
- `_RUNTIME_MODES`
- `_IDENTITY_KEYS`
- `_RUNTIME_PACKAGES`
- `python_environment_report(environment, package_names) -> dict[str, Any]`
- `require_python_environment(environment) -> dict[str, Any]`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`importlib.metadata`、`importlib.util`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`site`、`sys`、`typing`、`urllib.parse`

### `product/backend/infra/runtime/process/controlled/node_locator.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/controlled/node_locator.py) · Python AST；作用域内import不表示每次调用均执行。

- `controlled_node_executable(environ) -> Path`

静态import / dot-source：`hashlib`、`json`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.process.controlled.artifact`、`作用域内：product.protocols.runtime.portable_release`

### `product/backend/infra/runtime/process/controlled/node_owned.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/controlled/node_owned.py) · Python AST；作用域内import不表示每次调用均执行。

- `EXECUTOR`
- `node_artifact_store(var_dir) -> Path`
- `read_node_manifest(var_dir, request) -> tuple[Path, NodeRuntimeManifest]`
- `node_execution_identity(node_executable) -> dict[str, str]`
- `node_reference_matches(var_dir, request, reference, node_executable) -> bool`
- `node_corresponds(var_dir, reference, node_executable) -> bool`
- `class OwnedNodeProcess`
- `OwnedNodeProcess.stop(self)`
- `start_owned_node(var_dir, request, node_executable, environ, timeout, cancelled, record_owner_identity) -> OwnedNodeProcess`

静态import / dot-source：`__future__`、`dataclasses`、`hashlib`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.process.controlled.artifact`、`product.backend.infra.runtime.process.listeners`、`product.backend.infra.runtime.process.tree`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`subprocess`、`time`、`作用域内：product.backend.infra.runtime.process.records.record_server`

### `product/backend/infra/runtime/process/controlled/node_target.mjs`

[打开源码](../../../../../../../product/backend/infra/runtime/process/controlled/node_target.mjs) · JS/TS词法提取；re-export、条件和动态表达式需读源码确认。


静态import / dot-source：`node:async_hooks`、`node:crypto`、`node:fs`、`node:http`、`node:path`、`node:url`、`node:vm`

### `product/backend/infra/runtime/process/controlled/target.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/controlled/target.py) · Python AST；作用域内import不表示每次调用均执行。

- `main() -> int`

静态import / dot-source：`__future__`、`argparse`、`os`、`pathlib`、`product.backend.infra.runtime.process.controlled.artifact`、`product.protocols.runtime.runtime_identity`、`runpy`、`sys`

### `product/backend/infra/runtime/process/environment.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/environment.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProcessEnvironmentRole`
- `_COMMON_SOURCE_NAMES`
- `_ROLE_POLICIES`
- `_COMMON_IDENTITY_NAMES`
- `_RUNTIME_IDENTITY_NAMES`
- `_ALL_IDENTITY_NAMES`
- `_MAIN_PROCESS_ONLY_NAMES`
- `_FORCED_ENVIRONMENT_NAMES`
- `_ROLE_CONTROLLED_NAMES`
- `_CONTROLLED_NAME_CASEFOLDS`
- `_ENVIRONMENT_NAME_PATTERN`
- `_FAILURE_REASON_BY_MESSAGE`
- `process_environment_failure_summary(error) -> dict[str, object]`
- `minimal_process_environment(source, role, secret_names) -> dict[str, str]`
- `confirmed_python_executable(source) -> str`
- `python_module_command(source, module, *arguments) -> list[str]`
- `spawn_python_module(source, module, *arguments, role, secret_names, extra_environment, cwd, popen, python_executable, tree_name, before_release, **kwargs) -> subprocess.Popen[Any]`
- `run_python_module(source, module, *arguments, role, cwd, timeout_seconds, secret_names, extra_environment, python_executable) -> subprocess.CompletedProcess[str]`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`enum`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.tree`、`re`、`subprocess`、`sys`、`types`、`typing`、`uuid`

### `product/backend/infra/runtime/process/exclusive_file.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/exclusive_file.py) · Python AST；作用域内import不表示每次调用均执行。

- `open_exclusive_record_file(path)`

静态import / dot-source：`__future__`、`os`、`pathlib`、`作用域内：msvcrt`、`作用域内：pywintypes`、`作用域内：win32con`、`作用域内：win32file`

### `product/backend/infra/runtime/process/listeners.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/listeners.py) · Python AST；作用域内import不表示每次调用均执行。

- `ipv4_listeners(port) -> tuple[tuple[str, int], ...]`

静态import / dot-source：`ctypes`、`os`、`socket`、`struct`

### `product/backend/infra/runtime/process/lock.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/lock.py) · Python AST；作用域内import不表示每次调用均执行。

- `try_lock_stream(stream) -> bool`
- `unlock_stream(stream) -> None`
- `lock_is_available(path) -> bool`

静态import / dot-source：`__future__`、`os`、`pathlib`、`typing`、`作用域内：fcntl`、`作用域内：msvcrt`

### `product/backend/infra/runtime/process/records/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/records/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/runtime/process/records/record_capabilities.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/records/record_capabilities.py) · Python AST；作用域内import不表示每次调用均执行。

- `save_record_capability(var_dir, instance_id, value)`
- `read_record_capability(var_dir, instance_id) -> str`
- `discard_record_capability(var_dir, instance_id)`

静态import / dot-source：`pathlib`、`product.protocols.runtime.runtime_identity`、`pydantic`、`re`、`作用域内：win32crypt`

### `product/backend/infra/runtime/process/records/record_server.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/records/record_server.py) · Python AST；作用域内import不表示每次调用均执行。

- `record_store_path(var_dir, project_id) -> Path`
- `record_provider_fingerprint() -> str`
- `class OwnedRecordServer`
- `OwnedRecordServer.origin(self)`
- `OwnedRecordServer.reference(self, project_id, owner_identity)`
- `OwnedRecordServer.stop(self)`

静态import / dot-source：`__future__`、`hashlib`、`hmac`、`http.server`、`importlib`、`json`、`os`、`pathlib`、`product.backend.infra.observers.adapters.json_source`、`product.backend.infra.observers.records.transaction_store`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.transaction_records`、`pydantic`、`secrets`、`threading`、`urllib.parse`、`作用域内：product.backend.infra.observers.records`、`作用域内：product.backend.infra.runtime.process.records.record_capabilities`、`作用域内：product.backend.infra.runtime.process.tree`、`作用域内：product.protocols.runtime`、`动态引用：product.backend.infra.runtime.process.exclusive_file`、`动态引用：product.backend.infra.runtime.process.records.record_capabilities`

### `product/backend/infra/runtime/process/tree.py`

[打开源码](../../../../../../../product/backend/infra/runtime/process/tree.py) · Python AST；作用域内import不表示每次调用均执行。

- `_CONTROLLERS`
- `_NATIVE_POPEN`
- `class ProcessTreeController`
- `ProcessTreeController.attach(cls, process, native, tree_name) -> ProcessTreeController`
- `ProcessTreeController.kernel_identity(self) -> dict[str, str &#124; int]`
- `ProcessTreeController.has_exited(self) -> bool`
- `ProcessTreeController.terminate(self, timeout) -> None`
- `ProcessTreeController.release(self, timeout) -> None`
- `ProcessTreeController.close(self) -> None`
- `spawn_managed_process(command, popen, tree_name, **kwargs) -> subprocess.Popen[Any]`
- `controller_for(process) -> ProcessTreeController &#124; None`
- `release_process_tree(process, timeout) -> None`
- `terminate_process_tree(process, timeout) -> None`
- `process_tree_has_exited(process) -> bool`
- `kernel_tree_has_exited(identity) -> bool`
- `kernel_process_created_at(identity, process_id) -> int &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`ctypes`、`ctypes.wintypes`、`os`、`product.backend.core.errors`、`re`、`signal`、`subprocess`、`time`、`typing`、`weakref`

<!-- GENERATED:END -->
