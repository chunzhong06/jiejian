# 自动代码参考：backend/infra/storage/_root

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/storage/__init__.py`

[打开源码](../../../../../../../product/backend/infra/storage/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.base`、`.db`、`.execution.jobs`、`.execution.runs`、`.results.evidence`、`.results.finalizations`、`.results.findings`、`.results.gating`、`.unit_of_work`、`product.backend.infra.storage.applications.application_understanding`、`product.backend.infra.storage.applications.projects`、`product.backend.infra.storage.boundaries.contracts`、`product.backend.infra.storage.boundaries.permission_intents`、`product.backend.infra.storage.changes.source_changes`、`product.backend.infra.storage.execution.profiles`、`product.backend.infra.storage.preparation.action_preparation`、`product.backend.infra.storage.preparation.recordings`、`product.backend.infra.storage.preparation.test_identities`、`product.backend.infra.storage.settings.llm`

### `product/backend/infra/storage/base.py`

[打开源码](../../../../../../../product/backend/infra/storage/base.py) · Python AST；作用域内import不表示每次调用均执行。

- `NAMING_CONVENTION`
- `class Base`
- `_METADATA_KEY`
- `_SENSITIVE_METADATA_KEY`
- `_INLINE_SECRET`
- `class StorageRecord`
- `ensure_storage_payload_safe(value, known_secrets) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`product.backend.core.errors`、`pydantic`、`re`、`sqlalchemy`、`sqlalchemy.exc`、`sqlalchemy.orm`、`typing`

### `product/backend/infra/storage/db.py`

[打开源码](../../../../../../../product/backend/infra/storage/db.py) · Python AST；作用域内import不表示每次调用均执行。

- `SQLITE_BUSY_TIMEOUT_MS`
- `_BASE_MIGRATION_REVISION`
- `_MAINTENANCE_MIGRATION_REVISION`
- `_CURRENT_MIGRATION_REVISION`
- `_LEGACY_1_X_MIGRATION_REVISIONS`
- `_INCOMPATIBLE_DATABASE_MESSAGE`
- `_EXPECTED_TRIGGER_SQL`
- `default_database_path(var_dir) -> Path`
- `configure_sqlite_engine(engine) -> None`
- `create_sqlite_engine(database_path) -> Engine`
- `create_session_factory(engine) -> sessionmaker[Session]`
- `upgrade_database(database_path) -> None`
- `require_current_database(database_path) -> None`

静态import / dot-source：`__future__`、`alembic`、`alembic.config`、`collections`、`collections.abc`、`contextlib`、`importlib.resources`、`json`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`product.backend.infra.storage.base`、`product.backend.infra.storage.orm_registry`、`sqlalchemy`、`sqlalchemy.exc`、`sqlalchemy.orm`、`sqlalchemy.pool`、`sqlite3`、`tempfile`

### `product/backend/infra/storage/orm_registry.py`

[打开源码](../../../../../../../product/backend/infra/storage/orm_registry.py) · Python AST；作用域内import不表示每次调用均执行。

- `_STORAGE_ORM_MODULES`
- `load_storage_orm_mappings() -> None`

静态import / dot-source：`__future__`、`importlib`、`动态引用：未静态确定`

### `product/backend/infra/storage/unit_of_work.py`

[打开源码](../../../../../../../product/backend/infra/storage/unit_of_work.py) · Python AST；作用域内import不表示每次调用均执行。

- `class StorageUnitOfWork`
- `StorageUnitOfWork.begin(self) -> StorageUnitOfWork`
- `StorageUnitOfWork.commit(self) -> None`
- `StorageUnitOfWork.acquire_write_lock(self) -> None`
- `StorageUnitOfWork.rollback(self) -> None`
- `StorageUnitOfWork.close(self) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.infra.storage.applications.application_understanding`、`product.backend.infra.storage.applications.projects`、`product.backend.infra.storage.boundaries.business_boundaries`、`product.backend.infra.storage.boundaries.contracts`、`product.backend.infra.storage.boundaries.permission_intents`、`product.backend.infra.storage.boundaries.rule_candidates`、`product.backend.infra.storage.changes.code_observations`、`product.backend.infra.storage.changes.development`、`product.backend.infra.storage.changes.source_changes`、`product.backend.infra.storage.execution.job_control`、`product.backend.infra.storage.execution.jobs`、`product.backend.infra.storage.execution.profiles`、`product.backend.infra.storage.execution.runs`、`product.backend.infra.storage.preparation.action_preparation`、`product.backend.infra.storage.preparation.preparation_recovery`、`product.backend.infra.storage.preparation.proof_sources`、`product.backend.infra.storage.preparation.recordings`、`product.backend.infra.storage.preparation.supplemental_materials`、`product.backend.infra.storage.preparation.test_identities`、`product.backend.infra.storage.results.check_publications`、`product.backend.infra.storage.results.evidence`、`product.backend.infra.storage.results.finalizations`、`product.backend.infra.storage.results.findings`、`product.backend.infra.storage.results.gating`、`product.backend.infra.storage.runtime.environment_operations`、`product.backend.infra.storage.runtime.runtime_loads`、`product.backend.infra.storage.runtime.sample_workspaces`、`product.backend.infra.storage.settings.llm`、`sqlalchemy.exc`、`sqlalchemy.orm`、`types`

<!-- GENERATED:END -->
