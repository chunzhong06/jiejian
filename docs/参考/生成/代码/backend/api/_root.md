# 自动代码参考：backend/api/_root

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/api/__init__.py`

[打开源码](../../../../../../product/backend/api/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.app`

### `product/backend/api/app.py`

[打开源码](../../../../../../product/backend/api/app.py) · Python AST；作用域内import不表示每次调用均执行。

- `create_app(var_dir, control_origin, control_session_token, frontend_dir, start_worker, llm_transport, llm_secret_store, secret_store, environ, clock_us, folder_selector, shutdown_callback, official_sample_root) -> FastAPI`

静态import / dot-source：`__future__`、`asyncio`、`fastapi`、`fastapi.exceptions`、`logging`、`pathlib`、`product.backend`、`product.backend.api.errors`、`product.backend.api.frontend`、`product.backend.api.local_control`、`product.backend.api.mcp`、`product.backend.api.routers.applications.experience`、`product.backend.api.routers.applications.onboarding`、`product.backend.api.routers.applications.projects`、`product.backend.api.routers.boundaries.business_boundaries`、`product.backend.api.routers.boundaries.permission_drafts`、`product.backend.api.routers.changes.development`、`product.backend.api.routers.changes.source_changes`、`product.backend.api.routers.checks.checks`、`product.backend.api.routers.checks.results`、`product.backend.api.routers.checks.runs`、`product.backend.api.routers.preparation.preparation`、`product.backend.api.routers.preparation.recordings`、`product.backend.api.routers.preparation.supplemental_materials`、`product.backend.api.routers.preparation.test_identities`、`product.backend.api.routers.system.assistant`、`product.backend.api.routers.system.llm`、`product.backend.api.routers.system.mcp_access`、`product.backend.api.routers.system.system`、`product.backend.api.routers.workspace`、`product.backend.composition`、`product.backend.core.errors`、`product.backend.workflows.agent_access.service`、`pydantic`、`time`、`uuid`

### `product/backend/api/envelope.py`

[打开源码](../../../../../../product/backend/api/envelope.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ApiModel`
- `class ApiResponse`
- `data_response(value, status_code) -> JSONResponse`

静态import / dot-source：`__future__`、`fastapi.responses`、`pydantic`、`typing`

### `product/backend/api/errors.py`

[打开源码](../../../../../../product/backend/api/errors.py) · Python AST；作用域内import不表示每次调用均执行。

- `jiejian_error_handler(request, exc) -> JSONResponse`
- `request_validation_error_handler(request, exc) -> JSONResponse`
- `validation_error_handler(request, exc) -> JSONResponse`

静态import / dot-source：`__future__`、`fastapi`、`fastapi.exceptions`、`fastapi.responses`、`product.backend.core.errors`、`pydantic`

### `product/backend/api/frontend.py`

[打开源码](../../../../../../product/backend/api/frontend.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProductStaticFiles`
- `ProductStaticFiles.get_response(self, path, scope)`

静态import / dot-source：`fastapi.staticfiles`、`re`

### `product/backend/api/local_control.py`

[打开源码](../../../../../../product/backend/api/local_control.py) · Python AST；作用域内import不表示每次调用均执行。

- `class LocalControlDecision`
- `class LocalControlGuard`
- `LocalControlGuard.authorize(self, request) -> LocalControlDecision`
- `LocalControlGuard.issue_session_cookie(self, response) -> None`
- `LocalControlGuard.rejected_response(trace_id) -> JSONResponse`

静态import / dot-source：`__future__`、`dataclasses`、`fastapi`、`fastapi.responses`、`hmac`、`product.backend.core.errors`、`secrets`、`urllib.parse`

<!-- GENERATED:END -->
