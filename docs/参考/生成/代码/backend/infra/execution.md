# 自动代码参考：backend/infra/execution

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/execution/__init__.py`

[打开源码](../../../../../../product/backend/infra/execution/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/execution/check_executor.py`

[打开源码](../../../../../../product/backend/infra/execution/check_executor.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckExecutionOutput`
- `class CheckExecutor`
- `CheckExecutor.execute(self) -> CheckExecutionOutput`

静态import / dot-source：`__future__`、`dataclasses`、`pathlib`、`product.backend.core.errors`、`product.backend.core.lifecycle`、`product.backend.core.verification.checks`、`product.backend.infra.artifacts.checks.check_validation`、`product.backend.infra.execution.web.check_runtime`、`product.backend.infra.observers.checks.check_runtime`、`product.backend.infra.runtime.process.controlled.correspondence`、`product.backend.infra.runtime.process.controlled.node_locator`、`product.backend.infra.runtime.process.controlled.node_owned`、`product.protocols.checks.check_result`、`product.protocols.runtime.node_runtime`、`product.protocols.runtime.runtime_identity`、`time`

### `product/backend/infra/execution/port.py`

[打开源码](../../../../../../product/backend/infra/execution/port.py) · Python AST；作用域内import不表示每次调用均执行。

- `class ExecutionSnapshotView`
- `class TargetRuntimeContext`
- `class TargetBaselineResult`
- `class TargetObservationResult`
- `class TargetCleanupIssue`
- `class TargetCleanupError`
- `class TargetCaseSession`
- `TargetCaseSession.prepare(self) -> None`
- `TargetCaseSession.observe_target(self, spec, binding, correlation, phase) -> TargetObservationResult &#124; None`
- `TargetCaseSession.evaluate_baseline(self, baseline_envelopes, ignored_case_fields) -> TargetBaselineResult`
- `TargetCaseSession.execute_target(self) -> ExecutionFact`
- `TargetCaseSession.resolve_execution(self, observations) -> ExecutionFact`
- `TargetCaseSession.build_disclosure_proof(self, effect, resource_id, observations) -> DisclosureProof &#124; None`
- `TargetCaseSession.cleanup(self) -> None`
- `class TargetRuntime`
- `TargetRuntime.open_case(self, case, action) -> TargetCaseSession`
- `TargetRuntime.close(self) -> None`
- `class TargetRuntimeFactory`
- `TargetRuntimeFactory.create(self, snapshot, context) -> TargetRuntime`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`pathlib`、`product.backend.core.verification.differential`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions`、`product.backend.core.verification.permissions.coverage`、`product.protocols.observer`、`product.protocols.runner`、`product.protocols.runner.execution`、`typing`

### `product/backend/infra/execution/registry.py`

[打开源码](../../../../../../product/backend/infra/execution/registry.py) · Python AST；作用域内import不表示每次调用均执行。

- `_KIND`
- `class TargetRuntimeRegistry`
- `TargetRuntimeRegistry.register(self, factory) -> None`
- `TargetRuntimeRegistry.create(self, kind, snapshot, context) -> TargetRuntime`
- `TargetRuntimeRegistry.factory(self, kind) -> TargetRuntimeFactory`

静态import / dot-source：`__future__`、`product.backend.core.errors`、`product.backend.infra.execution.port`、`re`

### `product/backend/infra/execution/web/__init__.py`

[打开源码](../../../../../../product/backend/infra/execution/web/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/infra/execution/web/adapter.py`

[打开源码](../../../../../../product/backend/infra/execution/web/adapter.py) · Python AST；作用域内import不表示每次调用均执行。

- `_METADATA_ADDRESSES`
- `_EXPLICIT_PRIVATE_NETWORKS`
- `class HttpResponse`
- `class AuthorizedTarget`
- `class WebTargetGuard`
- `WebTargetGuard.authorize_path(self, path) -> AuthorizedTarget`
- `WebTargetGuard.authorize_url(self, url) -> AuthorizedTarget`
- `WebTargetGuard.authorize_redirect(self, current_url, location) -> AuthorizedTarget`
- `class HttpExecutionAdapter`
- `HttpExecutionAdapter.close(self) -> None`
- `HttpExecutionAdapter.execute(self, binding, case_id, action_id, classifier, slot_values, identity_runtime, terminal_completed) -> ExecutionFact`
- `HttpExecutionAdapter.execute_detailed(self, binding, case_id, action_id, classifier, slot_values, identity_runtime, terminal_completed, cleanup_request) -> tuple[ExecutionFact, HttpResponse]`
- `HttpExecutionAdapter.cleanup(self, path, case_id) -> None`
- `HttpExecutionAdapter.request(self, method, path, case_id, json_body, query, headers, data, body, slot_values, identity_runtime, bootstrap_request, auth_scope, redaction_values, cleanup_request, test_mode) -> HttpResponse`
- `extract_response_value(response, extractor) -> Any`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`hashlib`、`html.parser`、`httpx`、`ipaddress`、`json`、`product.backend.core.errors`、`product.backend.core.redaction`、`product.backend.core.verification.facts`、`product.protocols.web.identity`、`product.protocols.web.target`、`product.protocols.web.workflow`、`re`、`secrets`、`typing`、`urllib.parse`、`作用域内：hashlib`、`作用域内：product.backend.infra.execution.web.identity`

### `product/backend/infra/execution/web/check_runtime.py`

[打开源码](../../../../../../product/backend/infra/execution/web/check_runtime.py) · Python AST；作用域内import不表示每次调用均执行。

- `class CheckWebRuntime`
- `CheckWebRuntime.request_marker(self, case_id) -> str`
- `CheckWebRuntime.close(self)`
- `CheckWebRuntime.target_response(self, case_id)`
- `CheckWebRuntime.target_attempted(self, case_id) -> bool`
- `CheckWebRuntime.actual_identity_status(self, case_id) -> str`
- `CheckWebRuntime.identity_session(self, identity_id)`
- `CheckWebRuntime.verify_identity(self, identity_id, case, cleanup) -> str`
- `CheckWebRuntime.request(self, template, case, action_id, identity_id, cleanup) -> HttpResponse`
- `CheckWebRuntime.execute_flow(self, action, case, verify_identity)`
- `check_secret_names(bundle) -> tuple[str, ...]`

静态import / dot-source：`__future__`、`collections.abc`、`contextlib`、`os`、`product.backend.core.errors`、`product.backend.infra.execution.web.adapter`、`product.backend.infra.execution.web.identity`、`product.protocols.checks.check_runtime`、`product.protocols.checks.execution_request`、`product.protocols.web.request`、`product.protocols.web.response`、`re`、`typing`、`作用域内：product.protocols.checks.check_result`

### `product/backend/infra/execution/web/identity.py`

[打开源码](../../../../../../product/backend/infra/execution/web/identity.py) · Python AST；作用域内import不表示每次调用均执行。

- `class IdentityTokenState`
- `class HttpIdentityRuntime`
- `HttpIdentityRuntime.cookies(self) -> httpx.Cookies`
- `HttpIdentityRuntime.refresh_count(self) -> int`
- `HttpIdentityRuntime.redaction_secrets(self) -> tuple[str, ...]`
- `HttpIdentityRuntime.bootstrapped(self) -> bool`
- `HttpIdentityRuntime.close(self) -> None`
- `HttpIdentityRuntime.rebuild(self) -> HttpIdentityRuntime`
- `HttpIdentityRuntime.headers_for_request(self, origin) -> dict[str, str]`
- `HttpIdentityRuntime.bootstrap(self, send, requests) -> None`
- `HttpIdentityRuntime.refresh_once(self, send, token_expired) -> bool`
- `HttpIdentityRuntime.set_csrf(self, slot_id, value, origin, max_length) -> None`
- `HttpIdentityRuntime.slot_value(self, slot_id) -> str &#124; None`

静态import / dot-source：`__future__`、`collections.abc`、`dataclasses`、`httpx`、`json`、`product.backend.core.errors`、`product.protocols.web.identity`、`typing`、`urllib.parse`

### `product/backend/infra/execution/web/runtime.py`

[打开源码](../../../../../../product/backend/infra/execution/web/runtime.py) · Python AST；作用域内import不表示每次调用均执行。

- `class WebTargetRuntimeFactory`
- `WebTargetRuntimeFactory.create(self, snapshot, context) -> TargetRuntime`
- `class WebTargetRuntime`
- `WebTargetRuntime.open_case(self, case, action) -> TargetCaseSession`
- `WebTargetRuntime.close(self) -> None`
- `class WebTargetCaseSession`
- `WebTargetCaseSession.prepare(self) -> None`
- `WebTargetCaseSession.observe_target(self, spec, binding, correlation, phase) -> TargetObservationResult &#124; None`
- `WebTargetCaseSession.evaluate_baseline(self, baseline_envelopes, ignored_case_fields) -> TargetBaselineResult`
- `WebTargetCaseSession.execute_target(self) -> ExecutionFact`
- `WebTargetCaseSession.resolve_execution(self, observations) -> ExecutionFact`
- `WebTargetCaseSession.build_disclosure_proof(self, effect, resource_id, observations) -> DisclosureProof &#124; None`
- `WebTargetCaseSession.cleanup(self) -> None`

静态import / dot-source：`__future__`、`collections.abc`、`hashlib`、`hmac`、`json`、`os`、`product.backend.core.errors`、`product.backend.core.verification.facts`、`product.backend.core.verification.permissions`、`product.backend.core.verification.permissions.coverage`、`product.backend.infra.execution.port`、`product.backend.infra.execution.web.adapter`、`product.backend.infra.execution.web.identity`、`product.backend.infra.observers.adapters.owner_api`、`product.protocols`、`product.protocols.web.profile`、`product.protocols.web.workflow`、`secrets`、`typing`

<!-- GENERATED:END -->
