# 自动代码参考：backend/core/_root

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/core/__init__.py`

[打开源码](../../../../../../product/backend/core/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/core/development.py`

[打开源码](../../../../../../product/backend/core/development.py) · Python AST；作用域内import不表示每次调用均执行。

- `class DevelopmentTask`
- `class DevelopmentContext`
- `DevelopmentContext.ordered_permissions(self)`
- `class DevelopmentAcceptance`
- `class DevelopmentDelivery`
- `class DevelopmentReceipt`
- `DevelopmentReceipt.delivery_result(self)`
- `class RuntimeActivationReceipt`
- `RuntimeActivationReceipt.validate_receipt(self)`
- `class NodeRuntimeActivationReceipt`
- `NodeRuntimeActivationReceipt.validate_node_project(self)`

静态import / dot-source：`__future__`、`product.protocols.checks.execution_request`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`pydantic`、`typing`

### `product/backend/core/errors.py`

[打开源码](../../../../../../product/backend/core/errors.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ErrorCode`
- `class LLMWireErrorCode`
- `LLM_WIRE_TO_INTERNAL`
- `class JiejianError`
- `JiejianError.code(self) -> str`
- `JiejianError.to_dict(self) -> dict[str, Any]`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.redaction`、`typing`

### `product/backend/core/http_routes.py`

[打开源码](../../../../../../product/backend/core/http_routes.py) · Python AST；作用域内import不表示每次调用均执行。

- `HTTP_METHODS`
- `safe_route_path(path) -> bool`

静态import / dot-source：`__future__`

### `product/backend/core/identifiers.py`

[打开源码](../../../../../../product/backend/core/identifiers.py) · Python AST；作用域内import不表示每次调用均执行。

- `PROJECT_ID_PATTERN`
- `LONG_SLUG_ID_PATTERN`
- `RUN_ID_PATTERN`
- `JOB_ID_PATTERN`
- `RECORDING_ID_PATTERN`
- `TEST_IDENTITY_ID_PATTERN`
- `EVIDENCE_ID_PATTERN`
- `SHA256_PATTERN`
- `REQUIREMENT_ID_PATTERN`
- `CANDIDATE_ID_PATTERN`

### `product/backend/core/lifecycle.py`

[打开源码](../../../../../../product/backend/core/lifecycle.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProjectStatus`
- `class ContractStatus`
- `class RunLifecycle`
- `class RunVerdict`
- `class CaseVerdict`
- `class JobState`
- `class DomainModel`

静态import / dot-source：`__future__`、`enum`、`pydantic`、`typing`

### `product/backend/core/redaction.py`

[打开源码](../../../../../../product/backend/core/redaction.py) · Python AST；作用域内import不表示每次调用均执行。

- `REDACTED`
- `_SENSITIVE_KEY`
- `_BEARER`
- `_ASSIGNMENT`
- `redact(value) -> Any`
- `redact_known_secrets(value, secrets) -> Any`

静态import / dot-source：`__future__`、`collections.abc`、`re`、`typing`

<!-- GENERATED:END -->
