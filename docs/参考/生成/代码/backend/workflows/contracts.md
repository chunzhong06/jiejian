# 自动代码参考：backend/workflows/contracts

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/contracts/__init__.py`

[打开源码](../../../../../../product/backend/workflows/contracts/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/contracts/governance.py`

[打开源码](../../../../../../product/backend/workflows/contracts/governance.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ContractGovernance`
- `ContractGovernance.create_draft(self, project_id, contract_id, snapshot, sources, actor) -> ContractVersion`
- `ContractGovernance.revise_active(self, project_id, contract_id, snapshot, sources, actor) -> ContractVersion`
- `ContractGovernance.submit_review(self, project_id, contract_id, version, actor, available_observations) -> ContractVersion`
- `ContractGovernance.reject_review(self, project_id, contract_id, version, actor) -> ContractVersion`
- `ContractGovernance.activate_review(self, project_id, contract_id, version, actor, available_observations) -> ContractVersion`
- `ContractGovernance.list_versions(self, project_id, contract_id) -> tuple[ContractVersion, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.contracts.lifecycle`、`product.backend.core.contracts.models`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.permissions`、`product.backend.infra.storage`、`time`

<!-- GENERATED:END -->
