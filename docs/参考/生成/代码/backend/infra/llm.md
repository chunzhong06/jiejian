# 自动代码参考：backend/infra/llm

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/llm/__init__.py`

[打开源码](../../../../../../product/backend/infra/llm/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/llm/adapters/__init__.py`

[打开源码](../../../../../../product/backend/infra/llm/adapters/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.base`、`.deepseek`、`.gemini`、`.openai`、`.openai_compatible`

### `product/backend/infra/llm/adapters/base.py`

[打开源码](../../../../../../product/backend/infra/llm/adapters/base.py) · Python AST；作用域内import不表示每次调用均执行。

- `class LLMHttpRequest`
- `class LLMHttpResponse`
- `class LLMTransport`
- `LLMTransport.send(self, request) -> LLMHttpResponse`
- `class LLMTransportError`
- `class LLMAdapter`
- `LLMAdapter.build_request(self, profile, secret, prompt, reasoning_effort, json_schema) -> LLMHttpRequest`
- `LLMAdapter.parse_response(self, response) -> str`
- `json_body(payload) -> bytes`
- `max_output_tokens(profile) -> int`
- `class LLMInvokeResult`

静态import / dot-source：`__future__`、`dataclasses`、`json`、`product.backend.infra.llm.config`、`typing`

### `product/backend/infra/llm/adapters/deepseek.py`

[打开源码](../../../../../../product/backend/infra/llm/adapters/deepseek.py) · Python AST；作用域内import不表示每次调用均执行。

- `DEFAULT_BASE_URL`
- `class DeepSeekAdapter`
- `DeepSeekAdapter.build_request(self, profile, secret, prompt, reasoning_effort, json_schema) -> LLMHttpRequest`
- `DeepSeekAdapter.parse_response(self, response) -> str`

静态import / dot-source：`__future__`、`json`、`product.backend.infra.llm.adapters.base`、`product.backend.infra.llm.adapters.openai_compatible`、`product.backend.infra.llm.config`、`typing`

### `product/backend/infra/llm/adapters/gemini.py`

[打开源码](../../../../../../product/backend/infra/llm/adapters/gemini.py) · Python AST；作用域内import不表示每次调用均执行。

- `DEFAULT_BASE_URL`
- `class GeminiAdapter`
- `GeminiAdapter.build_request(self, profile, secret, prompt, reasoning_effort, json_schema) -> LLMHttpRequest`
- `GeminiAdapter.parse_response(self, response) -> str`

静态import / dot-source：`__future__`、`json`、`product.backend.infra.llm.adapters.base`、`product.backend.infra.llm.adapters.openai_compatible`、`product.backend.infra.llm.config`、`typing`、`urllib.parse`

### `product/backend/infra/llm/adapters/httpx_transport.py`

[打开源码](../../../../../../product/backend/infra/llm/adapters/httpx_transport.py) · Python AST；作用域内import不表示每次调用均执行。

- `class HttpxLLMTransport`
- `HttpxLLMTransport.send(self, request) -> LLMHttpResponse`

静态import / dot-source：`__future__`、`httpx`、`product.backend.infra.llm.adapters.base`

### `product/backend/infra/llm/adapters/openai.py`

[打开源码](../../../../../../product/backend/infra/llm/adapters/openai.py) · Python AST；作用域内import不表示每次调用均执行。

- `DEFAULT_BASE_URL`
- `class OpenAIAdapter`
- `OpenAIAdapter.build_request(self, profile, secret, prompt, reasoning_effort, json_schema) -> LLMHttpRequest`
- `OpenAIAdapter.parse_response(self, response) -> str`

静态import / dot-source：`__future__`、`json`、`product.backend.infra.llm.adapters.base`、`product.backend.infra.llm.adapters.openai_compatible`、`product.backend.infra.llm.config`、`typing`

### `product/backend/infra/llm/adapters/openai_compatible.py`

[打开源码](../../../../../../product/backend/infra/llm/adapters/openai_compatible.py) · Python AST；作用域内import不表示每次调用均执行。

- `class OpenAICompatibleAdapter`
- `OpenAICompatibleAdapter.build_request(self, profile, secret, prompt, reasoning_effort, json_schema) -> LLMHttpRequest`
- `OpenAICompatibleAdapter.parse_response(self, response) -> str`

静态import / dot-source：`__future__`、`json`、`product.backend.infra.llm.adapters.base`、`product.backend.infra.llm.config`、`typing`

### `product/backend/infra/llm/catalog.py`

[打开源码](../../../../../../product/backend/infra/llm/catalog.py) · Python AST；作用域内import不表示每次调用均执行。

- `class LLMModelOption`
- `class LLMModelCatalog`
- `_MAX_MODELS`
- `_MAX_GEMINI_PAGES`
- `_BASE_URLS`
- `class LLMModelCatalogService`
- `LLMModelCatalogService.discover(self, provider, secret, base_url, allow_local_http) -> LLMModelCatalog`
- `LLMModelCatalogService.refresh(self, profile, secret) -> LLMModelCatalog`

静态import / dot-source：`__future__`、`dataclasses`、`json`、`product.backend.core.errors`、`product.backend.infra.llm.adapters.base`、`product.backend.infra.llm.adapters.openai_compatible`、`product.backend.infra.llm.config`、`typing`、`urllib.parse`、`作用域内：product.backend.infra.llm.config`

### `product/backend/infra/llm/config.py`

[打开源码](../../../../../../product/backend/infra/llm/config.py) · Python AST；作用域内import不表示每次调用均执行。

- `PROFILE_NAME_PATTERN`
- `_MODEL_NAME`
- `ENV_SECRET_REF_PATTERN`
- `_ENV_SECRET_REF`
- `_HOSTNAME`
- `class LLMProviderType`
- `class LLMConfigModel`
- `class LLMProfileConfig`
- `LLMProfileConfig.parse_provider(cls, value) -> LLMProviderType`
- `LLMProfileConfig.validate_printable_text(cls, value) -> str`
- `LLMProfileConfig.normalize_base_url(cls, value, info) -> str &#124; None`
- `LLMProfileConfig.validate_secret_ref(cls, value) -> str &#124; None`
- `LLMProfileConfig.validate_profile(self) -> LLMProfileConfig`
- `class AIAssistanceSettings`
- `AIAssistanceSettings.validate_enabled_default(self) -> AIAssistanceSettings`
- `validate_secret_ref(value) -> str`
- `validate_credential_secret_ref(value) -> str`
- `_KNOWN_REASONING_OPTIONS`
- `reasoning_options_for(provider, model) -> tuple[str, ...]`
- `normalize_llm_base_url(value, allow_local_http, require_local_http_authorization) -> str`

静态import / dot-source：`__future__`、`enum`、`ipaddress`、`posixpath`、`product.backend.infra.secrets.refs`、`pydantic`、`re`、`typing`、`urllib.parse`

### `product/backend/infra/llm/profiles.py`

[打开源码](../../../../../../product/backend/infra/llm/profiles.py) · Python AST；作用域内import不表示每次调用均执行。

- `class LLMProfileView`
- `class LLMProfileRegistry`
- `LLMProfileRegistry.available(self) -> bool`
- `LLMProfileRegistry.get_settings(self) -> AIAssistanceSettings`
- `LLMProfileRegistry.update_settings(self, enabled, default_profile_name) -> AIAssistanceSettings`
- `LLMProfileRegistry.discover_models(self, provider, secret, base_url, allow_local_http) -> LLMModelCatalog`
- `LLMProfileRegistry.refresh_models(self, profile_name) -> LLMModelCatalog`
- `LLMProfileRegistry.save_default_profile(self, values, secret) -> LLMProfileView`
- `LLMProfileRegistry.list(self) -> tuple[LLMProfileView, ...]`
- `LLMProfileRegistry.get(self, profile_name) -> LLMProfileView`
- `LLMProfileRegistry.create(self, values, secret) -> LLMProfileView`
- `LLMProfileRegistry.update(self, profile_name, values, secret) -> LLMProfileView`
- `LLMProfileRegistry.test_connection(self, profile_name) -> LLMProfileView`
- `LLMProfileRegistry.resolve_provider(self, profile_name) -> ResolvedLLMProvider`

静态import / dot-source：`__future__`、`collections.abc`、`os`、`product.backend.core.errors`、`product.backend.infra.llm.adapters.base`、`product.backend.infra.llm.catalog`、`product.backend.infra.llm.config`、`product.backend.infra.llm.provider`、`product.backend.infra.secrets`、`product.backend.infra.storage`、`pydantic`、`threading`、`time`、`typing`

### `product/backend/infra/llm/provider.py`

[打开源码](../../../../../../product/backend/infra/llm/provider.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ResolvedLLMProvider`
- `ResolvedLLMProvider.invoke(self, prompt, reasoning_effort, json_schema) -> LLMInvokeResult`
- `adapter_for(provider) -> LLMAdapter`
- `probe_provider(transport, profile, secret, prompt) -> None`

静态import / dot-source：`__future__`、`dataclasses`、`product.backend.core.errors`、`product.backend.infra.llm.adapters.base`、`product.backend.infra.llm.adapters.deepseek`、`product.backend.infra.llm.adapters.gemini`、`product.backend.infra.llm.adapters.openai`、`product.backend.infra.llm.adapters.openai_compatible`、`product.backend.infra.llm.config`、`time`、`typing`

<!-- GENERATED:END -->
