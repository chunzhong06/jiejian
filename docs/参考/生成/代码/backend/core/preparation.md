# 自动代码参考：backend/core/preparation

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/core/preparation/__init__.py`

[打开源码](../../../../../../product/backend/core/preparation/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/core/preparation/bindings.py`

[打开源码](../../../../../../product/backend/core/preparation/bindings.py) · Python AST；作用域内import不表示每次调用均执行。

- `_UNSAFE_TEXT`
- `_SECRET_KEY`
- `class ResourceInjectionKind`
- `class ActionEvidenceKind`
- `class ResourceInjection`
- `ResourceInjection.validate_location(self) -> ResourceInjection`
- `class RecordedRequestTemplate`
- `RecordedRequestTemplate.validate_relative_path(cls, value) -> str`
- `RecordedRequestTemplate.validate_body(self) -> RecordedRequestTemplate`
- `contains_resource_slot(value) -> bool`
- `class RegisteredObserverReference`
- `class ActionExecutionBinding`
- `class ActionResourceBinding`
- `ActionResourceBinding.validate_resource_id(cls, value) -> str`
- `class ActionEvidenceBinding`
- `ActionEvidenceBinding.validate_source(self) -> ActionEvidenceBinding`
- `class ActionRecoveryBinding`
- `ActionRecoveryBinding.validate_recovery(self) -> ActionRecoveryBinding`
- `binding_fingerprint(model_type, values) -> str`
- `seal_binding(model_type, **values)`

静态import / dot-source：`__future__`、`enum`、`json`、`product.backend.core.boundaries.entities`、`product.backend.core.identifiers`、`product.backend.core.redaction`、`pydantic`、`re`、`typing`、`urllib.parse`

### `product/backend/core/preparation/requirements.py`

[打开源码](../../../../../../product/backend/core/preparation/requirements.py) · Python AST；作用域内import不表示每次调用均执行。

- `class AllocationMode`
- `class AssuranceStatus`
- `class PermissionIdentity`
- `class IdentityRequirementSlot`
- `class PermissionIdentitySlots`
- `class IdentityRequirementPlan`
- `class ActionResourceRequirement`
- `class EffectEvidenceRequirement`
- `class AllowControlRequirement`
- `class ActionAllowControlBinding`
- `class ActionAssuranceContract`
- `class IdentityRequirementPlanner`
- `IdentityRequirementPlanner.plan(self, permissions, controls) -> IdentityRequirementPlan`
- `compile_action_assurance(action, permissions, allow_control_bindings) -> ActionAssuranceContract`

静态import / dot-source：`__future__`、`collections`、`enum`、`product.backend.core.boundaries.entities`、`product.backend.core.boundaries.permissions`、`product.backend.core.boundaries.semantics`、`product.backend.core.identifiers`、`pydantic`

<!-- GENERATED:END -->
