# 自动代码参考：backend/infra/identity

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/identity/__init__.py`

[打开源码](../../../../../../product/backend/infra/identity/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.infra.identity.browser`

### `product/backend/infra/identity/browser.py`

[打开源码](../../../../../../product/backend/infra/identity/browser.py) · Python AST；作用域内import不表示每次调用均执行。

- `_CREDENTIAL_SECRET_MAX_BYTES`
- `class IdentityPreparationBrowserAdapter`
- `IdentityPreparationBrowserAdapter.run(self, request, secret_store, ready_callback, save_requested, cancellation_requested, before_secret_write, interaction, error_observer, now_us, monotonic) -> IdentityPreparationResult`

静态import / dot-source：`__future__`、`collections.abc`、`playwright.sync_api`、`product.backend.core.errors`、`product.backend.core.identities.models`、`product.backend.infra.execution.web.adapter`、`product.backend.infra.recording.transport`、`product.backend.infra.secrets`、`product.protocols`、`product.protocols.web.target`、`time`、`urllib.parse`

### `product/backend/infra/identity/control.py`

[打开源码](../../../../../../product/backend/infra/identity/control.py) · Python AST；作用域内import不表示每次调用均执行。

- `_MARKERS`
- `class IdentityPreparationControlPaths`
- `identity_preparation_control_paths(root) -> IdentityPreparationControlPaths`
- `write_identity_preparation_marker(path, root) -> bool`
- `valid_identity_preparation_marker(path) -> bool`

静态import / dot-source：`__future__`、`dataclasses`、`os`、`pathlib`、`product.backend.core.errors`、`uuid`

### `product/backend/infra/identity/process.py`

[打开源码](../../../../../../product/backend/infra/identity/process.py) · Python AST；作用域内import不表示每次调用均执行。

- `IDENTITY_PREPARATION_EXIT_OK`
- `IDENTITY_PREPARATION_EXIT_PROTOCOL`
- `IDENTITY_PREPARATION_EXIT_INTERNAL`
- `_ATTEMPT_DIR_ENV`
- `execute_identity_preparation(stdin, stdout, stderr, environ, adapter) -> int`
- `main() -> int`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.identity.browser`、`product.backend.infra.identity.control`、`product.backend.infra.secrets`、`product.protocols`、`sys`、`typing`、`uuid`

<!-- GENERATED:END -->
