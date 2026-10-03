# 自动代码参考：backend/workflows/onboarding

> 自动生成。当前源码结构与注册投影，不代表运行验收或完整调用图。

<!-- GENERATED:START -->

### `product/backend/workflows/onboarding/__init__.py`

[打开源码](../../../../../../product/backend/workflows/onboarding/__init__.py) · Python AST；作用域内import不表示每次调用均执行。


### `product/backend/workflows/onboarding/discovery.py`

[打开源码](../../../../../../product/backend/workflows/onboarding/discovery.py) · Python AST；作用域内import不表示每次调用均执行。

- `_ALLOWED_NAMES`
- `_AUTH_DEPENDENCY_MARKERS`
- `_SCRIPT_NAME`
- `_IGNORED_DIRECTORY_NAMES`
- `_READ_BUDGET_MESSAGE`
- `is_reparse_point(path) -> bool`
- `canonical_folder(path) -> Path`
- `discover_folder(path, limits) -> DiscoveryResult`

静态import / dot-source：`__future__`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.workflows.onboarding.models`、`re`、`stat`、`tomllib`、`typing`

### `product/backend/workflows/onboarding/folder_picker_process.py`

[打开源码](../../../../../../product/backend/workflows/onboarding/folder_picker_process.py) · Python AST；作用域内import不表示每次调用均执行。

- `show_directory_dialog(platform_name, tk_module, filedialog_module) -> str`
- `main() -> int`

静态import / dot-source：`__future__`、`json`、`os`、`product.backend.workflows.onboarding.models`、`typing`、`作用域内：tkinter`

### `product/backend/workflows/onboarding/models.py`

[打开源码](../../../../../../product/backend/workflows/onboarding/models.py) · Python AST；作用域内import不表示每次调用均执行。

- `class OnboardingModel`
- `class DiscoveryLimits`
- `class DiscoveryCandidate`
- `class DiscoveryHint`
- `class DiscoveryMissingItem`
- `class DiscoveryWarning`
- `class DiscoveryResult`
- `class FolderSelectionResult`

静态import / dot-source：`__future__`、`pydantic`、`typing`

### `product/backend/workflows/onboarding/workflow.py`

[打开源码](../../../../../../product/backend/workflows/onboarding/workflow.py) · Python AST；作用域内import不表示每次调用均执行。

- `class FolderSelector`
- `FolderSelector.select_folder(self) -> FolderSelectionResult`
- `class SystemFolderSelector`
- `SystemFolderSelector.select_folder(self) -> FolderSelectionResult`
- `class OnboardingWorkflow`
- `OnboardingWorkflow.select_folder(self) -> FolderSelectionResult`
- `OnboardingWorkflow.inspect(self, path) -> DiscoveryResult`

静态import / dot-source：`__future__`、`collections.abc`、`json`、`os`、`pathlib`、`product.backend.core.errors`、`product.backend.infra.runtime.paths`、`product.backend.infra.runtime.process.environment`、`product.backend.workflows.onboarding.discovery`、`product.backend.workflows.onboarding.models`、`subprocess`、`threading`、`typing`

<!-- GENERATED:END -->
