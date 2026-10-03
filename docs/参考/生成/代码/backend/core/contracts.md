# 自动代码参考：backend/core/contracts

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/core/contracts/__init__.py`

[打开源码](../../../../../../product/backend/core/contracts/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/core/contracts/execution_binding.py`

[打开源码](../../../../../../product/backend/core/contracts/execution_binding.py) · Python AST；作用域内import不表示每次调用均执行。

- `resolve_execution_contract(record, governed) -> PermissionContract`

静态import / dot-source：`__future__`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.permissions`、`typing`

### `product/backend/core/contracts/lifecycle.py`

[打开源码](../../../../../../product/backend/core/contracts/lifecycle.py) · Python AST；作用域内import不表示每次调用均执行。

- `_CONTRACT_TRANSITIONS`
- `transition_contract_version(contract, target, actor, occurred_at_us) -> ContractVersion`
- `revise_contract_version(active, snapshot, provenance, actor, occurred_at_us) -> ContractVersion`

静态import / dot-source：`product.backend.core.contracts.models`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.permissions`

### `product/backend/core/contracts/models.py`

[打开源码](../../../../../../product/backend/core/contracts/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ContractSourceType`
- `class ContractAuditAction`
- `class GovernanceModel`
- `class SourceReference`
- `SourceReference.validate_locator(cls, value) -> str`
- `class ContractProvenance`
- `ContractProvenance.validate_references(self) -> ContractProvenance`
- `class ContractAuditEntry`
- `ContractAuditEntry.validate_actor(cls, value) -> str`
- `class ContractVersion`
- `ContractVersion.validate_version(self) -> ContractVersion`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.identifiers`、`product.backend.core.lifecycle`、`product.backend.core.verification.permissions`、`pydantic`

<!-- GENERATED:END -->
