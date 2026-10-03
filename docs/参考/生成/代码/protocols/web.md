# 自动代码参考：protocols/web

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/protocols/web/__init__.py`

[打开源码](../../../../../product/protocols/web/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`.request`、`.response`、`.workflow`

### `product/protocols/web/base.py`

[打开源码](../../../../../product/protocols/web/base.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ProtocolModel`

静态import / dot-source：`pydantic`

### `product/protocols/web/identity.py`

[打开源码](../../../../../product/protocols/web/identity.py) · Python AST；作用域内import不表示每次调用均执行。

- `_IDENTIFIER`
- `PROJECT_ID_PATTERN`
- `_PATH`
- `class HttpIdentityKind`
- `class IdentityBootstrapRequest`
- `class AuthTargetScope`
- `AuthTargetScope.validate_scope(self) -> AuthTargetScope`
- `class BearerIdentityBinding`
- `class StaticHeaderCredential`
- `StaticHeaderCredential.reject_reserved_name(cls, value) -> str`
- `class StaticHeadersIdentityBinding`
- `StaticHeadersIdentityBinding.validate_headers(self) -> StaticHeadersIdentityBinding`
- `class CookieSessionIdentityBinding`
- `class PreparedCookieCredential`
- `PreparedCookieCredential.validate_cookie(self) -> PreparedCookieCredential`
- `class PreparedCookieSessionIdentityBinding`
- `PreparedCookieSessionIdentityBinding.validate_cookies(self) -> PreparedCookieSessionIdentityBinding`
- `class LoginWorkflowIdentityBinding`
- `class OAuth2ClientCredentialsIdentityBinding`
- `class OAuth2RefreshTokenIdentityBinding`
- `class WebExecutionIdentity`
- `WebExecutionIdentity.validate_bootstrap(self) -> WebExecutionIdentity`
- `binding_secret_refs(value) -> tuple[str, ...]`
- `required_identity_secret_refs(identity) -> tuple[str, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`ipaddress`、`product.protocols.web.base`、`product.protocols.web.workflow`、`pydantic`、`typing`、`urllib.parse`

### `product/protocols/web/profile.py`

[打开源码](../../../../../product/protocols/web/profile.py) · Python AST；作用域内import不表示每次调用均执行。

- `WEB_EXECUTION_PROFILE_MAX_BYTES`
- `_PROFILE_ID`
- `_SECRET_KEY`
- `_INLINE_SECRET`
- `class WebExecutionSnapshot`
- `WebExecutionSnapshot.validate_snapshot(self) -> WebExecutionSnapshot`
- `required_web_secret_refs(snapshot) -> tuple[str, ...]`
- `class WebExecutionProfile`
- `WebExecutionProfile.validate_profile(self) -> WebExecutionProfile`
- `WebExecutionProfile.build_snapshot(self, contract, plan) -> WebExecutionSnapshot`
- `canonical_web_execution_profile_json_bytes(profile, known_secrets) -> bytes`
- `web_execution_profile_sha256(profile, known_secrets) -> str`
- `parse_web_execution_profile(raw, known_secrets) -> WebExecutionProfile`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`json`、`math`、`product.backend.core.errors`、`product.backend.core.verification.differential`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions`、`product.backend.core.verification.permissions.coverage`、`product.protocols.observer`、`product.protocols.runner.execution`、`product.protocols.web.identity`、`product.protocols.web.target`、`product.protocols.web.workflow`、`pydantic`、`re`、`typing`、`作用域内：product.backend.core.verification.permissions`

### `product/protocols/web/request.py`

[打开源码](../../../../../product/protocols/web/request.py) · Python AST；作用域内import不表示每次调用均执行。

- `HTTP_TEMPLATE_MAX_BYTES`
- `HTTP_TEMPLATE_MAX_DEPTH`
- `HTTP_TEMPLATE_MAX_FIELDS`
- `HTTP_JSON_PATH_MAX_DEPTH`
- `HTTP_SELECTOR_MAX_LENGTH`
- `HTTP_LITERAL_MAX_LENGTH`
- `HTTP_SLOT_MAX_LENGTH`
- `CASE_SUBJECT_IDENTITY`
- `_IDENTIFIER`
- `_PATH`
- `_SECRET_NAME`
- `_CODE_MARKER`
- `_JSON_PATH`
- `_STEP_NUMBER`
- `class HttpBodyKind`
- `class ValueSlotSource`
- `class ValueSlotConsumer`
- `class ValueType`
- `class ValueSlot`
- `ValueSlot.validate_slot(self) -> ValueSlot`
- `class HttpParameter`
- `HttpParameter.validate_value(self) -> HttpParameter`
- `class MultipartPart`
- `MultipartPart.validate_source(self) -> MultipartPart`
- `class EmptyBody`
- `class JsonBody`
- `JsonBody.validate_value(self) -> JsonBody`
- `class FormUrlEncodedBody`
- `class MultipartBody`
- `class HttpRequestTemplate`
- `HttpRequestTemplate.reject_reserved_headers(cls, values) -> tuple[HttpParameter, ...]`
- `HttpRequestTemplate.validate_references(self) -> HttpRequestTemplate`

静态import / dot-source：`__future__`、`collections.abc`、`enum`、`math`、`product.protocols.web.base`、`pydantic`、`re`、`typing`

### `product/protocols/web/response.py`

[打开源码](../../../../../product/protocols/web/response.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ResponseExtractorKind`
- `class HttpPredicateKind`
- `class HttpOutcome`
- `class ResponseExtractor`
- `ResponseExtractor.validate_extractor(self) -> ResponseExtractor`
- `class HttpPredicate`
- `HttpPredicate.validate_predicate(self) -> HttpPredicate`
- `class HttpOutcomeClassifier`
- `HttpOutcomeClassifier.classify(self, response, terminal_completed) -> HttpOutcome`

静态import / dot-source：`.request`、`__future__`、`collections.abc`、`enum`、`html.parser`、`json`、`product.protocols.web.base`、`pydantic`、`re`、`typing`

### `product/protocols/web/target.py`

[打开源码](../../../../../product/protocols/web/target.py) · Python AST；作用域内import不表示每次调用均执行。

- `class WebTargetScope`
- `WebTargetScope.normalize_hosts(cls, values) -> tuple[str, ...]`
- `WebTargetScope.normalize_ports(cls, values) -> tuple[int, ...]`
- `WebTargetScope.validate_scope(self) -> WebTargetScope`
- `class WebTargetDefinition`

静态import / dot-source：`__future__`、`ipaddress`、`product.protocols.web.base`、`pydantic`、`typing`、`urllib.parse`

### `product/protocols/web/workflow.py`

[打开源码](../../../../../product/protocols/web/workflow.py) · Python AST；作用域内import不表示每次调用均执行。

- `class WorkflowStepPurpose`
- `class WorkflowFailurePolicy`
- `class ResetStrategyKind`
- `class BaselineIntegrityMode`
- `class LogicalResourceSlot`
- `class BaselineProjection`
- `class ResetEndpointStrategy`
- `class UniqueResourceWorkflowResetStrategy`
- `class SnapshotProviderResetStrategy`
- `class ResetNotRequiredStrategy`
- `class BaselineFingerprint`
- `class BaselineIntegrity`
- `class HttpWorkflowStep`
- `HttpWorkflowStep.validate_step(self) -> HttpWorkflowStep`
- `class HttpWorkflowBinding`
- `HttpWorkflowBinding.validate_workflow(self) -> HttpWorkflowBinding`
- `build_baseline_fingerprint(logical_resource_handle, normalized_resource_state, workflow_state, relationship_projection, effect_projection, normalization_version, projection_version) -> BaselineFingerprint`

静态import / dot-source：`.request`、`.response`、`__future__`、`collections.abc`、`enum`、`hashlib`、`json`、`product.protocols.web.base`、`pydantic`、`re`、`typing`

<!-- GENERATED:END -->
