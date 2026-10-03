# 自动代码参考：backend/infra/samples

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/infra/samples/__init__.py`

[打开源码](../../../../../../product/backend/infra/samples/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


静态import / dot-source：`product.backend.infra.samples.official`

### `product/backend/infra/samples/official.py`

[打开源码](../../../../../../product/backend/infra/samples/official.py) · Python AST；作用域内import不表示每次调用均执行。

- `_MANIFEST_FIELDS`
- `_EXPECTED_MANIFEST`
- `_EXPERIENCE_ID`
- `_MAX_MANIFEST_BYTES`
- `_SECRET_NAMES`
- `_PATH_SECRET_NAMES`
- `_AUTHORIZATION_POLICY_FILE`
- `class OfficialSampleInstallation`
- `class OfficialSampleRuntime`
- `OfficialSampleRuntime.check_descriptor_path(self) -> Path`
- `class OfficialSampleManager`
- `OfficialSampleManager.active(self) -> OfficialSampleRuntime &#124; None`
- `OfficialSampleManager.start(self, experience_id, authorization_order, owner_observation, blob_observation, execution_mode, workspace_id) -> OfficialSampleRuntime`
- `OfficialSampleManager.switch_behavior(self, experience_id, authorization_order, owner_observation, blob_observation, execution_mode) -> OfficialSampleRuntime`
- `OfficialSampleManager.runtime_reference(self, experience_id) -> ControlledRuntimeReference &#124; None`
- `OfficialSampleManager.reload_source(self, experience_id, expected_source_fingerprint) -> OfficialSampleRuntime`
- `OfficialSampleManager.resolve_secret_names(self, names) -> dict[str, str]`
- `OfficialSampleManager.set_observation(self, experience_id, available) -> None`
- `OfficialSampleManager.export_execution_mode(self, experience_id) -> str`
- `OfficialSampleManager.bind_effects(self, experience_id, export_effect_id, view_effect_id) -> None`
- `OfficialSampleManager.workspace_source(self, workspace_id) -> Path`
- `OfficialSampleManager.cleanup_exited_instance(self, instance_id, identity) -> None`
- `OfficialSampleManager.stop(self, experience_id) -> None`

静态import / dot-source：`__future__`、`ast`、`collections.abc`、`dataclasses`、`httpx`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.controlled.artifact`、`product.backend.infra.runtime.process.controlled.correspondence`、`product.backend.infra.runtime.process.environment`、`product.backend.infra.runtime.process.tree`、`product.protocols.runtime.runtime_identity`、`re`、`secrets`、`shutil`、`subprocess`、`threading`、`time`、`typing`、`urllib.parse`、`uuid`、`作用域内：product.backend.infra.runtime.process.tree`

<!-- GENERATED:END -->
