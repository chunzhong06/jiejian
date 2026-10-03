# 自动代码参考：backend/infra/storage/applications

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/storage/applications/__init__.py`

[打开源码](../../../../../../../product/backend/infra/storage/applications/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/storage/applications/application_understanding.py`

[打开源码](../../../../../../../product/backend/infra/storage/applications/application_understanding.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ApplicationUnderstandingRow`
- `class ApplicationUnderstandingRepository`
- `ApplicationUnderstandingRepository.add(self, record) -> None`
- `ApplicationUnderstandingRepository.get(self, project_id) -> ApplicationUnderstanding &#124; None`
- `ApplicationUnderstandingRepository.get_by_source_root(self, source_root) -> ApplicationUnderstanding &#124; None`
- `ApplicationUnderstandingRepository.replace(self, record) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`product.backend.core.applications.models`、`product.backend.core.errors`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

### `product/backend/infra/storage/applications/projects.py`

[打开源码](../../../../../../../product/backend/infra/storage/applications/projects.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProjectRow`
- `class ProjectRecord`
- `ProjectRecord.validate_time_order(self) -> ProjectRecord`
- `class ProjectRepository`
- `ProjectRepository.add(self, record) -> None`
- `ProjectRepository.get(self, project_id) -> ProjectRecord &#124; None`
- `ProjectRepository.list_all(self) -> tuple[ProjectRecord, ...]`
- `ProjectRepository.replace(self, record) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.core.recording.models`、`product.backend.core.verification.permissions`、`product.backend.infra.storage.base`、`product.protocols`、`pydantic`、`re`、`sqlalchemy`、`sqlalchemy.exc`、`sqlalchemy.orm`、`time`、`typing`

<!-- GENERATED:END -->
