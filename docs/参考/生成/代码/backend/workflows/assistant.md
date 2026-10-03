# 自动代码参考：backend/workflows/assistant

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/assistant/__init__.py`

[打开源码](../../../../../../product/backend/workflows/assistant/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.workflows.assistant.diagnosis`、`product.backend.workflows.assistant.templates`

### `product/backend/workflows/assistant/cache.py`

[打开源码](../../../../../../product/backend/workflows/assistant/cache.py) · Python AST；作用域内import不表示每次调用均执行。

- `class AssistantCache`
- `AssistantCache.read(self, subject_id, template_id, fingerprint, surface_input) -> dict[str, Any] &#124; None`
- `AssistantCache.write_success(self, subject_id, template_id, fingerprint, provider, profile, model, reasoning_setting, suggestions, generated_at_us) -> None`
- `AssistantCache.write_failure(self, subject_id, template_id, fingerprint, code, retry_after_us) -> None`

静态import / dot-source：`__future__`、`hashlib`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.workflows.assistant.templates`、`tempfile`、`typing`

### `product/backend/workflows/assistant/current_surfaces.py`

[打开源码](../../../../../../product/backend/workflows/assistant/current_surfaces.py) · Python AST；作用域内import不表示每次调用均执行。

- `CURRENT_ASSISTANT_TEMPLATES`
- `class PreparationAssistantSurfaceResolver`
- `PreparationAssistantSurfaceResolver.resolve_result(self, run_id)`
- `PreparationAssistantSurfaceResolver.resolve_project(self, project_id, template_id, business_actor_id, business_action_id, recording_id)`

静态import / dot-source：`__future__`、`collections`、`product.backend.core.applications.models`、`product.backend.core.boundaries.entities`、`product.backend.core.errors`、`product.backend.core.identifiers`、`product.backend.core.recording.models`、`product.backend.workflows.assistant.surfaces`、`product.backend.workflows.assistant.templates`、`product.backend.workflows.preparation.models`、`product.backend.workflows.recording.source`、`re`、`urllib.parse`

### `product/backend/workflows/assistant/diagnosis.py`

[打开源码](../../../../../../product/backend/workflows/assistant/diagnosis.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ErrorArea`
- `class ErrorPhase`
- `class ErrorIntervention`
- `class RecoveryAction`
- `class ErrorDiagnosisContext`
- `ErrorDiagnosisContext.validate_unique(cls, values) -> tuple[object, ...]`
- `class ErrorDiagnosis`
- `_SELF_TARGET`
- `_SESSION_EXPIRED`
- `_OBSERVER_INCOMPLETE`
- `_EXACT_PRESENTATIONS`
- `_CLEANUP_WARNINGS`
- `diagnose_error(context) -> ErrorDiagnosis`

静态import / dot-source：`__future__`、`enum`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.protocols.runner`、`pydantic`、`typing`

### `product/backend/workflows/assistant/service.py`

[打开源码](../../../../../../product/backend/workflows/assistant/service.py) · Python AST；作用域内import不表示每次调用均执行。

- `class AssistantStatus`
- `class AssistantSurfaceView`
- `class AssistantService`
- `AssistantService.get_project(self, project_id, template_id, business_actor_id, business_action_id, recording_id) -> AssistantSurfaceView`
- `AssistantService.generate_project(self, project_id, template_id, retry, business_actor_id, business_action_id, recording_id) -> AssistantSurfaceView`
- `AssistantService.get_result(self, run_id) -> AssistantSurfaceView`
- `AssistantService.generate_result(self, run_id, retry) -> AssistantSurfaceView`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`product.backend.core.errors`、`product.backend.infra.llm.adapters.base`、`product.backend.infra.llm.profiles`、`product.backend.workflows.assistant.cache`、`product.backend.workflows.assistant.surfaces`、`product.backend.workflows.assistant.templates`、`pydantic`、`re`、`threading`、`time`

### `product/backend/workflows/assistant/surfaces.py`

[打开源码](../../../../../../product/backend/workflows/assistant/surfaces.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ResolvedAssistantSurface`
- `class AssistantSurfaceResolver`
- `AssistantSurfaceResolver.resolve_project(self, project_id, template_id, **references) -> ResolvedAssistantSurface`
- `AssistantSurfaceResolver.resolve_result(self, run_id) -> ResolvedAssistantSurface`

静态import / dot-source：`.templates`、`__future__`、`collections.abc`、`dataclasses`、`typing`

### `product/backend/workflows/assistant/templates.py`

[打开源码](../../../../../../product/backend/workflows/assistant/templates.py) · Python AST；作用域内import不表示每次调用均执行。

- `class AssistantTemplateId`
- `class AssistantEntityType`
- `class AssistantSuggestionKind`
- `class AssistantTemplateSpec`
- `class AssistantFact`
- `AssistantFact.validate_safe_value(self) -> AssistantFact`
- `class AssistantEntity`
- `AssistantEntity.validate_unique_facts(self) -> AssistantEntity`
- `class AssistantSurfaceInput`
- `AssistantSurfaceInput.validate_unique_values(self) -> AssistantSurfaceInput`
- `class AssistantSuggestion`
- `AssistantSuggestion.validate_entity_ids(cls, values) -> tuple[str, ...]`
- `AssistantSuggestion.validate_explanation(cls, value) -> str`
- `class AssistantResult`
- `ASSISTANT_SAFETY_INSTRUCTIONS`
- `ASSISTANT_TEMPLATES`
- `build_surface_input(template_id, subject_id, facts, entities) -> AssistantSurfaceInput`
- `render_assistant_prompt(value) -> str`
- `assistant_result_json_schema(value) -> dict[str, object]`
- `parse_assistant_result(raw, surface_input) -> AssistantResult`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`json`、`product.backend.core.errors`、`pydantic`、`re`、`typing`

<!-- GENERATED:END -->
