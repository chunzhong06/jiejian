# 自动代码参考：backend/infra/runtime/_root

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/runtime/__init__.py`

[打开源码](../../../../../../../product/backend/infra/runtime/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.paths`

### `product/backend/infra/runtime/diagnostics.py`

[打开源码](../../../../../../../product/backend/infra/runtime/diagnostics.py) · Python AST；作用域内import不表示每次调用均执行。

- `class DoctorCheck`
- `class DoctorReport`
- `browser_availability() -> str`
- `runtime_environment_details() -> dict[str, Any]`
- `run_doctor(config_path, cli_overrides, project_root) -> DoctorReport`
- `human_lines(report) -> tuple[str, ...]`

静态import / dot-source：`__future__`、`importlib.metadata`、`ipaddress`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.core.redaction`、`product.backend.infra.runtime.logging`、`product.backend.infra.runtime.process.controlled.identity`、`product.backend.infra.runtime.settings`、`pydantic`、`shutil`、`socket`、`sqlite3`、`subprocess`、`sys`、`tempfile`、`typing`、`作用域内：playwright.sync_api`、`作用域内：re`

### `product/backend/infra/runtime/frontend_assets.py`

[打开源码](../../../../../../../product/backend/infra/runtime/frontend_assets.py) · Python AST；作用域内import不表示每次调用均执行。

- `frontend_asset_identity(directory) -> dict`

静态import / dot-source：`hashlib`、`json`、`pathlib`、`product.protocols.runtime.frontend_assets`、`pydantic`

### `product/backend/infra/runtime/logging.py`

[打开源码](../../../../../../../product/backend/infra/runtime/logging.py) · Python AST；作用域内import不表示每次调用均执行。

- `class JsonFormatter`
- `JsonFormatter.format(self, record) -> str`
- `configure_logging(level, stream, trace_id, var_dir, console, known_secrets) -> stdlib_logging.Logger`

静态import / dot-source：`__future__`、`collections.abc`、`datetime`、`json`、`logging`、`logging.handlers`、`pathlib`、`product.backend.core.redaction`、`product.backend.infra.runtime.paths`、`sys`、`typing`

### `product/backend/infra/runtime/maintenance.py`

[打开源码](../../../../../../../product/backend/infra/runtime/maintenance.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ORPHAN_MIN_AGE_SECONDS`
- `_LOG_MAX_AGE_SECONDS`
- `_LOG_KEEP_PER_CATEGORY`
- `_SESSION_MTIME_TOLERANCE_SECONDS`
- `_PLAN_TTL_SECONDS`
- `_OPERATIONS`
- `class MaintenanceCandidate`
- `class MaintenancePlan`
- `class LocalMaintenanceService`
- `LocalMaintenanceService.status(self) -> dict[str, object]`
- `LocalMaintenanceService.operate(self, operation, confirmed, dry_run, plan_id) -> dict[str, object]`
- `LocalMaintenanceService.preview(self, operation) -> dict[str, object]`
- `LocalMaintenanceService.execute(self, plan_id, expected_scope) -> dict[str, object]`
- `LocalMaintenanceService.startup_maintenance(self) -> dict[str, object]`

静态import / dot-source：`__future__`、`collections.abc`、`contextlib`、`dataclasses`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.lock`、`secrets`、`shutil`、`time`

### `product/backend/infra/runtime/paths.py`

[打开源码](../../../../../../../product/backend/infra/runtime/paths.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RuntimePaths`
- `RuntimePaths.data(self) -> Path`
- `RuntimePaths.database(self) -> Path`
- `RuntimePaths.jobs(self) -> Path`
- `RuntimePaths.projects(self) -> Path`
- `RuntimePaths.reports(self) -> Path`
- `RuntimePaths.artifact_checks(self) -> Path`
- `RuntimePaths.runtime(self) -> Path`
- `RuntimePaths.build_runtime(self) -> Path`
- `RuntimePaths.frontend_dist(self) -> Path`
- `RuntimePaths.worker_runtime(self) -> Path`
- `RuntimePaths.identity_preparations(self) -> Path`
- `RuntimePaths.official_sample_runtime(self) -> Path`
- `RuntimePaths.python_runtime(self) -> Path`
- `RuntimePaths.locks(self) -> Path`
- `RuntimePaths.cache(self) -> Path`
- `RuntimePaths.assistant_cache(self) -> Path`
- `RuntimePaths.logs(self) -> Path`
- `RuntimePaths.startup_logs(self) -> Path`
- `RuntimePaths.worker_logs(self) -> Path`
- `RuntimePaths.runner_logs(self) -> Path`
- `RuntimePaths.recording_logs(self) -> Path`
- `RuntimePaths.identity_preparation_logs(self) -> Path`
- `RuntimePaths.app_logs(self) -> Path`
- `RuntimePaths.official_sample_logs(self) -> Path`
- `RuntimePaths.audit(self) -> Path`
- `RuntimePaths.competition_audit(self) -> Path`
- `RuntimePaths.temp(self) -> Path`
- `RuntimePaths.process_gates(self) -> Path`
- `RuntimePaths.test(self) -> Path`
- `RuntimePaths.ensure_layout(self) -> RuntimePaths`

静态import / dot-source：`__future__`、`dataclasses`、`pathlib`

### `product/backend/infra/runtime/serve_lock.py`

[打开源码](../../../../../../../product/backend/infra/runtime/serve_lock.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ServeLock`
- `ServeLock.acquire(cls, var_dir, conflict_code, conflict_message) -> ServeLock`
- `ServeLock.release(self) -> None`

静态import / dot-source：`__future__`、`dataclasses`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.lock`、`secrets`、`typing`

### `product/backend/infra/runtime/service_lifetime.py`

[打开源码](../../../../../../../product/backend/infra/runtime/service_lifetime.py) · Python AST；作用域内import不表示每次调用均执行。

- `serve_owner_is_alive(path, owner_token) -> bool`

静态import / dot-source：`__future__`、`json`、`pathlib`、`product.backend.infra.runtime.process.lock`

### `product/backend/infra/runtime/session_secrets.py`

[打开源码](../../../../../../../product/backend/infra/runtime/session_secrets.py) · Python AST；作用域内import不表示每次调用均执行。

- `class SessionSecretOverlay`
- `SessionSecretOverlay.set_session(self, session_id, reference, value)`
- `SessionSecretOverlay.clear_session(self, session_id)`
- `SessionSecretOverlay.clear(self)`
- `SessionSecretOverlay.read(self, reference)`
- `SessionSecretOverlay.configured(self, reference)`
- `SessionSecretOverlay.write(self, reference, value)`
- `SessionSecretOverlay.delete(self, reference)`

静态import / dot-source：`threading`

### `product/backend/infra/runtime/settings.py`

[打开源码](../../../../../../../product/backend/infra/runtime/settings.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ENVIRONMENT_KEYS`
- `class Settings`
- `Settings.paths(self) -> RuntimePaths`
- `Settings.validate_schema_version(cls, value) -> str`
- `Settings.normalize_log_level(cls, value) -> str`
- `class LoadedSettings`
- `default_config_path() -> Path &#124; None`
- `load_settings(config_path, cli_overrides, environ, default_path) -> LoadedSettings`

静态import / dot-source：`__future__`、`dataclasses`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`pydantic`、`tomllib`、`typing`

<!-- GENERATED:END -->
