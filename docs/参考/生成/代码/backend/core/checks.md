# 自动代码参考：backend/core/checks

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/core/checks/__init__.py`

[打开源码](../../../../../../product/backend/core/checks/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/core/checks/plan.py`

[打开源码](../../../../../../product/backend/core/checks/plan.py) · Python AST；作用域内import不表示每次调用均执行。

- `class RegisteredEffectProofCapability`
- `class PreparedIdentityAssignment`
- `class CheckPlanGap`
- `class CheckCase`
- `class CheckTwin`
- `class ActionCheckPlan`
- `class ProjectCheckPlan`
- `class PreparedActionInput`
- `classify_http_resource_presence(status, same_resource, same_run, redirected)`
- `derive_effect_proof(effect, binding, resource_id, capabilities)`
- `compile_project_check_plan(project_id, source_fingerprint, policy_epoch, engine_version, config_fingerprint, actions)`

静态import / dot-source：`__future__`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.preparation.bindings`、`product.backend.core.preparation.requirements`、`product.protocols.checks.execution_request`、`pydantic`、`typing`、`urllib.parse`、`作用域内：json`

### `product/backend/core/checks/repair.py`

[打开源码](../../../../../../product/backend/core/checks/repair.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CurrentRepairReference`
- `class RepairCaseIdentity`
- `RepairCaseIdentity.validate_effect_set(self)`
- `RepairCaseIdentity.fingerprint(self) -> str`
- `repair_case_identity(action, case) -> RepairCaseIdentity`
- `repair_evidence_standards(action, case, bundle) -> tuple[str, ...]`
- `class RepairCaseRequirement`
- `RepairCaseRequirement.validate_sets(self)`
- `class CurrentRepairContract`
- `CurrentRepairContract.validate_contract(self)`
- `CurrentRepairContract.reference(self) -> CurrentRepairReference`
- `repair_context(contract) -> RepairContext`
- `current_request_permissions(request) -> tuple[PermissionReference, ...]`
- `class CurrentRepairVerification`
- `verify_current_repair(contract, request, bundle, result, evidence, expected_change_context) -> CurrentRepairVerification`

静态import / dot-source：`__future__`、`product.backend.core.lifecycle`、`product.backend.core.verification.breakpoints`、`product.backend.core.verification.checks`、`product.protocols.checks.execution_request`、`pydantic`、`typing`

<!-- GENERATED:END -->
