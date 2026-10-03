# 自动代码参考：backend/infra/secrets

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/secrets/__init__.py`

[打开源码](../../../../../../product/backend/infra/secrets/__init__.py) · Python AST；作用域内import不表示每次调用均执行。

- `default_secret_store() -> SecretStore`

静态import / dot-source：`os`、`product.backend.infra.secrets.refs`、`product.backend.infra.secrets.store`、`product.backend.infra.secrets.windows`

### `product/backend/infra/secrets/refs.py`

[打开源码](../../../../../../product/backend/infra/secrets/refs.py) · Python AST；作用域内import不表示每次调用均执行。

- `_SEGMENT`
- `_NAMESPACE_DEPTHS`
- `credential_ref(namespace, *segments) -> str`
- `validate_credential_secret_ref(value) -> str`

静态import / dot-source：`__future__`、`re`

### `product/backend/infra/secrets/store.py`

[打开源码](../../../../../../product/backend/infra/secrets/store.py) · Python AST；作用域内import不表示每次调用均执行。

- `class SecretStore`
- `SecretStore.write(self, secret_ref, secret) -> None`
- `SecretStore.read(self, secret_ref) -> str &#124; None`
- `SecretStore.delete(self, secret_ref) -> None`
- `SecretStore.configured(self, secret_ref) -> bool`
- `class UnavailableSecretStore`
- `UnavailableSecretStore.write(self, secret_ref, secret) -> None`
- `UnavailableSecretStore.read(self, secret_ref) -> str &#124; None`
- `UnavailableSecretStore.delete(self, secret_ref) -> None`
- `UnavailableSecretStore.configured(self, secret_ref) -> bool`

静态import / dot-source：`__future__`、`product.backend.core.errors`、`typing`

### `product/backend/infra/secrets/windows.py`

[打开源码](../../../../../../product/backend/infra/secrets/windows.py) · Python AST；作用域内import不表示每次调用均执行。

- `_MAX_CREDENTIAL_BLOB_BYTES`
- `class WindowsCredentialManagerSecretStore`
- `WindowsCredentialManagerSecretStore.write(self, secret_ref, secret) -> None`
- `WindowsCredentialManagerSecretStore.read(self, secret_ref) -> str &#124; None`
- `WindowsCredentialManagerSecretStore.delete(self, secret_ref) -> None`
- `WindowsCredentialManagerSecretStore.configured(self, secret_ref) -> bool`

静态import / dot-source：`__future__`、`ctypes`、`os`、`product.backend.infra.secrets.refs`

<!-- GENERATED:END -->
