# 自动代码参考：backend/workflows/agent_access

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/agent_access/__init__.py`

[打开源码](../../../../../../product/backend/workflows/agent_access/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/agent_access/client_config.py`

[打开源码](../../../../../../product/backend/workflows/agent_access/client_config.py) · Python AST；作用域内import不表示每次调用均执行。

- `CLIENTS`
- `class ConnectionProblem`
- `read_config(path) -> str`
- `json_patch(text, entry, zcode, fallback) -> str`
- `toml_patch(text, entry) -> str`
- `dsh_patch(text, entry) -> str`
- `trae_link(entry) -> str`
- `dsh_needs_startup_update(text) -> bool`
- `connection_matches(client, text, entry) -> bool`

静态import / dot-source：`__future__`、`base64`、`json`、`pathlib`、`re`、`tomllib`、`urllib.parse`、`yaml`

### `product/backend/workflows/agent_access/connection_files.py`

[打开源码](../../../../../../product/backend/workflows/agent_access/connection_files.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ConnectionProfile`
- `ConnectionProfile.loopback_only(cls, value)`
- `class ConnectionReceipt`
- `class ConnectionBackup`
- `protect(value) -> bytes`
- `unprotect(value) -> bytes`
- `atomic_write(path, value) -> None`
- `read_profile(path) -> ConnectionProfile`

静态import / dot-source：`__future__`、`os`、`pathlib`、`pydantic`、`tempfile`、`typing`、`urllib.parse`、`作用域内：win32crypt`

### `product/backend/workflows/agent_access/connections.py`

[打开源码](../../../../../../product/backend/workflows/agent_access/connections.py) · Python AST；作用域内import不表示每次调用均执行。

- `class AgentConnections`
- `AgentConnections.install(self, client, profile)`
- `AgentConnections.status(self, client)`
- `AgentConnections.restore(self, client)`

静态import / dot-source：`__future__`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.workflows.agent_access.client_config`、`product.backend.workflows.agent_access.connection_files`、`product.backend.workflows.agent_access.connector`、`shutil`、`sys`、`threading`、`uuid`

### `product/backend/workflows/agent_access/connector.py`

[打开源码](../../../../../../product/backend/workflows/agent_access/connector.py) · Python AST；作用域内import不表示每次调用均执行。

- `MESSAGES`
- `class ResumeRejected`
- `class IdleInput`
- `IdleInput.readline(self, _limit)`
- `relay(profile, source, destination, secret_store, http, observe, reload_profile, diagnose)`
- `main() -> int`

静态import / dot-source：`__future__`、`httpx`、`json`、`mcp.shared.inbound`、`mcp_types`、`pathlib`、`product.backend.infra.secrets`、`product.backend.workflows.agent_access.connection_files`、`product.backend.workflows.agent_access.dsh_schema`、`product.backend.workflows.agent_access.service`、`queue`、`sys`、`threading`、`time`

### `product/backend/workflows/agent_access/dsh_schema.py`

[打开源码](../../../../../../product/backend/workflows/agent_access/dsh_schema.py) · Python AST；作用域内import不表示每次调用均执行。

- `class DshSchemaError`
- `project_schema(schema) -> dict`
- `class DshToolSchemas`
- `DshToolSchemas.adapt(self, payload) -> dict`
- `DshToolSchemas.validate(self, name, arguments) -> bool`
- `DshToolSchemas.validation_issues(self, name, arguments) -> list[dict[str, str]]`

静态import / dot-source：`__future__`、`copy`、`jsonschema`、`jsonschema.exceptions`

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

### `product/backend/workflows/agent_access/workflow.py`

[打开源码](../../../../../../product/backend/workflows/agent_access/workflow.py) · Python AST；作用域内import不表示每次调用均执行。

- `class AgentWorkflowContext`
- `AgentWorkflowContext.read(self, project_id, stage, recording_id, run_id, case_id)`

静态import / dot-source：`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.workflows.recording.source`、`pydantic_core`、`re`、`urllib.parse`

<!-- GENERATED:END -->
