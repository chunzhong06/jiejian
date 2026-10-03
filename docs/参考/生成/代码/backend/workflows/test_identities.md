# 自动代码参考：backend/workflows/test_identities

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/test_identities/__init__.py`

[打开源码](../../../../../../product/backend/workflows/test_identities/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.workflows.test_identities.service`

### `product/backend/workflows/test_identities/execution.py`

[打开源码](../../../../../../product/backend/workflows/test_identities/execution.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ENVIRONMENT_NAME`
- `class TestIdentityExecutionCredentials`
- `TestIdentityExecutionCredentials.profile_identity(self, record) -> WebExecutionIdentity`
- `TestIdentityExecutionCredentials.resolve(self, names) -> Mapping[str, str]`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.core.identities.models`、`product.backend.infra.secrets`、`product.backend.workflows.test_identities.service`、`product.protocols`、`re`

### `product/backend/workflows/test_identities/preparation.py`

[打开源码](../../../../../../product/backend/workflows/test_identities/preparation.py) · Python AST；作用域内import不表示每次调用均执行。

- `class IdentityPreparationStatus`
- `class IdentityPreparationView`
- `class IdentityPreparationManager`
- `IdentityPreparationManager.active_runtime_paths(self) -> tuple[Path, ...]`
- `IdentityPreparationManager.start(self, identity_id) -> IdentityPreparationView`
- `IdentityPreparationManager.status(self, preparation_id) -> IdentityPreparationView`
- `IdentityPreparationManager.confirm(self, preparation_id) -> IdentityPreparationView`
- `IdentityPreparationManager.cancel(self, preparation_id) -> IdentityPreparationView`
- `IdentityPreparationManager.close(self) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`enum`、`json`、`pathlib`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.identities.models`、`product.backend.infra.identity.control`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.backend.infra.secrets`、`product.backend.workflows.test_identities.service`、`product.protocols`、`product.protocols.web.target`、`pydantic`、`re`、`shutil`、`subprocess`、`threading`、`time`、`urllib.parse`、`uuid`

### `product/backend/workflows/test_identities/service.py`

[打开源码](../../../../../../product/backend/workflows/test_identities/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class TestIdentityStatus`
- `class PreparedLoginState`
- `class TestIdentityView`
- `class TestIdentityService`
- `TestIdentityService.create(self, project_id, actor_id, actor_revision, label) -> TestIdentityView`
- `TestIdentityService.list(self, project_id) -> tuple[TestIdentityView, ...]`
- `TestIdentityService.get(self, identity_id) -> TestIdentityView`
- `TestIdentityService.get_record(self, identity_id) -> TestIdentity`
- `TestIdentityService.save_prepared_state(self, identity_id, state) -> TestIdentityView`
- `TestIdentityService.reset(self, identity_id) -> TestIdentityView`
- `TestIdentityService.delete(self, identity_id) -> None`
- `TestIdentityService.remove_project_credentials(self, project_id) -> int`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.identities.models`、`product.backend.infra.secrets.store`、`product.backend.infra.storage`、`pydantic`、`time`、`uuid`

<!-- GENERATED:END -->
