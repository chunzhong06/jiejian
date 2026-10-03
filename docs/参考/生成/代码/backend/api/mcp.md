# 自动代码参考：backend/api/mcp

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/api/mcp/__init__.py`

[打开源码](../../../../../../product/backend/api/mcp/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.api.mcp.server`

### `product/backend/api/mcp/errors.py`

[打开源码](../../../../../../product/backend/api/mcp/errors.py) · Python AST；作用域内import不表示每次调用均执行。

- `_T`
- `_ACCESS_ERROR_CODES`
- `require_mcp_level(access, ctx, required_level, project_id) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`mcp`、`mcp.server.mcpserver`、`product.backend.core.errors`、`product.backend.workflows.agent_access.service`、`pydantic`、`typing`

### `product/backend/api/mcp/preparation.py`

[打开源码](../../../../../../product/backend/api/mcp/preparation.py) · Python AST；作用域内import不表示每次调用均执行。

- `public_preparation(value)`
- `register_preparation_tools(server, context, access, require_level, invoke, client_name)`

静态import / dot-source：`json`、`mcp.server.mcpserver`、`product.backend.workflows.agent_access.service`、`product.backend.workflows.preparation.proofs.commands`、`typing`

### `product/backend/api/mcp/server.py`

[打开源码](../../../../../../product/backend/api/mcp/server.py) · Python AST；作用域内import不表示每次调用均执行。

- `_REQUEST_CLIENT`
- `class MCPControl`
- `build_mcp_control(context, access, control_origin, control_host) -> MCPControl`

静态import / dot-source：`__future__`、`collections.abc`、`contextvars`、`dataclasses`、`json`、`mcp.server`、`mcp.server.context`、`mcp.server.mcpserver`、`mcp.server.transport_security`、`product.backend`、`product.backend.api.mcp.errors`、`product.backend.api.mcp.transport`、`product.backend.api.mcp.views`、`product.backend.composition`、`product.backend.core.boundaries.rule_candidates`、`product.backend.core.checks.repair`、`product.backend.core.development`、`product.backend.core.errors`、`product.backend.infra.runtime.diagnostics`、`product.backend.workflows.agent_access.service`、`starlette.types`、`typing`、`作用域内：product.backend.api.mcp.preparation`

### `product/backend/api/mcp/transport.py`

[打开源码](../../../../../../product/backend/api/mcp/transport.py) · Python AST；作用域内import不表示每次调用均执行。

- `class MCPBearerGuard`
- `class MCPPathAdapter`

静态import / dot-source：`__future__`、`product.backend.api.mcp.errors`、`product.backend.core.errors`、`product.backend.workflows.agent_access.service`、`starlette.datastructures`、`starlette.responses`、`starlette.types`

### `product/backend/api/mcp/views.py`

[打开源码](../../../../../../product/backend/api/mcp/views.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`__future__`、`pydantic`、`typing`、`作用域内：product.backend.workflows.checks.repairs.repair_text`

<!-- GENERATED:END -->
