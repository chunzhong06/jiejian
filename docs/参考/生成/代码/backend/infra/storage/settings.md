# 自动代码参考：backend/infra/storage/settings

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/storage/settings/__init__.py`

[打开源码](../../../../../../../product/backend/infra/storage/settings/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/storage/settings/llm.py`

[打开源码](../../../../../../../product/backend/infra/storage/settings/llm.py) · Python AST；作用域内import不表示每次调用均执行。

- `class LLMProfileRow`
- `class AIAssistanceSettingsRow`
- `class LLMProfileRepository`
- `LLMProfileRepository.add(self, profile) -> None`
- `LLMProfileRepository.get(self, profile_name) -> LLMProfileConfig &#124; None`
- `LLMProfileRepository.list(self) -> tuple[LLMProfileConfig, ...]`
- `LLMProfileRepository.replace(self, profile) -> None`
- `class AIAssistanceSettingsRepository`
- `AIAssistanceSettingsRepository.get(self) -> AIAssistanceSettings`
- `AIAssistanceSettingsRepository.replace(self, settings) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`product.backend.core.errors`、`product.backend.infra.llm.config`、`product.backend.infra.storage.base`、`sqlalchemy`、`sqlalchemy.orm`

<!-- GENERATED:END -->
