# 自动代码参考：backend/workflows/agent_access

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/agent_access/__init__.py`

[打开源码](../../../../../../product/backend/workflows/agent_access/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/agent_access/service.py`

[打开源码](../../../../../../product/backend/workflows/agent_access/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `MCP_PAIRING_SECRET_REF`
- `class MCPAccessLevel`
- `class MCPConnectionState`
- `_LEVEL_ORDER`
- `class MCPProjectGrant`
- `class MCPAccessView`
- `class MCPAccessCredentialView`
- `class MCPAccessController`
- `MCPAccessController.view(self) -> MCPAccessView`
- `MCPAccessController.pair(self) -> MCPAccessCredentialView`
- `MCPAccessController.rotate(self) -> MCPAccessCredentialView`
- `MCPAccessController.resume(self) -> MCPAccessView`
- `MCPAccessController.reveal(self) -> MCPAccessCredentialView`
- `MCPAccessController.pause(self) -> MCPAccessView`
- `MCPAccessController.forget(self) -> MCPAccessView`
- `MCPAccessController.set_level(self, project_id, level) -> MCPAccessView`
- `MCPAccessController.execution_authority(self, project_id) -> str`
- `MCPAccessController.execution_authority_active(self, project_id, authority_id) -> bool`
- `MCPAccessController.level_for(self, project_id) -> MCPAccessLevel`
- `MCPAccessController.authorize(self, authorization) -> None`
- `MCPAccessController.require(self, authorization, required_level, project_id) -> None`
- `MCPAccessController.close(self) -> None`
- `MCPAccessController.note_activity(self, client_name, client_version) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`hmac`、`product.backend.core.errors`、`product.backend.infra.secrets`、`pydantic`、`secrets`、`threading`、`time`、`typing`、`作用域内：uuid`

<!-- GENERATED:END -->
