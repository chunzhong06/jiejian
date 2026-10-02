# 自动代码参考：开发脚本

> 生成区域只描述当前代码结构；职责与安全理由由能力映射和任务指南维护。

<!-- GENERATED:START -->

<!-- 此区域由 scripts/docs/generate.py 从 scripts/ 读取。 -->

### `scripts/build/hatch_build.py`
- `class CustomBuildHook`
主要 import / dot-source：`__future__`, `hatchling.builders.hooks.plugin.interface`, `os`, `pathlib`

### `scripts/build/portable.py`
- `RELEASE_VERSION`
- `RELEASE_NAME`
- `FULL_ARCHIVE`
- `NOSAMPLES_ARCHIVE`
- `_FORBIDDEN_PARTS`
- `_TEXT_SUFFIXES`
- `_START_CMD`
- `_START_PS1`
- `_README`
- `build(arguments) -> None`
- `main() -> None`
主要 import / dot-source：`__future__`, `argparse`, `collections.abc`, `hashlib`, `json`, `os`, `pathlib`, `product.backend`, `product.protocols.portable_release`, `shutil`, `subprocess`, `sys`, `zipfile`

### `scripts/dev/commands.ps1`
- `function Invoke-DevelopmentCli`
- `function Invoke-DevelopmentShell`
- `function Invoke-DevelopmentStart`
- `function Invoke-DevelopmentTest`
- `function Invoke-Docs`
- `function Invoke-FrontendTest`
- `function Invoke-Schema`
- `function Invoke-Verification`
- `function jiejian`
- `function quit`

### `scripts/dev/common.ps1`
- `function Enter-PrepareLock`
- `function Exit-PrepareLock`
- `function Fail-Development`
- `function Get-CombinedDigest`
- `function Get-FileDigest`
- `function Get-PathSetDigest`
- `function Get-StateValue`
- `function Invoke-External`
- `function Read-State`
- `function Read-Toolchain`
- `function Restore-CallerEnvironment`
- `function Save-CallerEnvironment`
- `function Save-State`
- `function Set-StateValue`
- `function Write-PrepareStatus`

### `scripts/dev/frontend.ps1`
- `function Copy-FrontendBuildToInstance`
- `function Get-FrontendBuildDigest`
- `function Get-FrontendBuildRoot`
- `function Get-FrontendDependencyDigest`
- `function Get-FrontendEditorPluginRoot`
- `function Get-FrontendEditorPluginTarget`
- `function Get-FrontendSourceInputs`
- `function Get-FrontendWorkspace`
- `function Install-FrontendEditorPlugin`
- `function Invoke-FrontendBuild`
- `function Prepare-FrontendWorkspace`
- `function Prepare-SourceFrontend`
- `function Publish-FrontendBuild`
- `function Read-FrontendBuildReceipt`
- `function Remove-LegacyFrontendArtifacts`
- `function Resolve-DevelopmentNode`
- `function Set-FrontendToolEnvironment`
- `function Sync-FrontendWorkspaceSources`
- `function Test-FrontendBuild`
- `function Test-FrontendEditorPluginInstalled`

### `scripts/dev/package.ps1`
- `function Invoke-Package`

### `scripts/dev/prepare.ps1`
- `function Get-DownloadActivityToken`
- `function Invoke-ExternalWithProgressTimeout`
- `function Prepare-Chromium`
- `function Prepare-Database`
- `function Prepare-SourceRuntime`
- `function Stop-ExternalProcessTree`
- `function Write-SourceReceipt`

### `scripts/dev/python.ps1`
- `function Confirm-DevelopmentIdentity`
- `function Ensure-Conda`
- `function Get-ProjectPackageTopologyInputs`
- `function Get-ProjectSyncInputs`
- `function Invoke-Update`
- `function Prepare-Python`
- `function Read-DevelopmentIdentity`
- `function Resolve-CondaPrefix`
- `function Resolve-DocsPython`
- `function Resolve-Uv`
- `function Set-DevelopmentEnvironment`
- `function Sync-Project`
- `function Test-CondaPython`

### `scripts/dev/sample-test.ps1`
- `function Invoke-SampleTest`

### `scripts/dev.ps1`
- `function Test-CommandContract`
- `param $Command`
- `param $ForcePrepare`
- `param $Update`
- `param $VarDir`
主要 import / dot-source：`$PSScriptRoot/dev/commands.ps1`, `$PSScriptRoot/dev/common.ps1`, `$PSScriptRoot/dev/frontend.ps1`, `$PSScriptRoot/dev/package.ps1`, `$PSScriptRoot/dev/prepare.ps1`, `$PSScriptRoot/dev/python.ps1`, `$PSScriptRoot/dev/sample-test.ps1`

### `scripts/docs/generate.py`
- `START`
- `END`
- `CODE_GROUPS`
- `generate(root, update) -> list[Path]`
- `main() -> int`
主要 import / dot-source：`__future__`, `argparse`, `ast`, `pathlib`, `re`, `sys`, `urllib.parse`

### `scripts/start.ps1`
- `param $DisplaySpinnerAscii`
- `param $DisplaySpinnerProcess`
- `param $DisplaySpinnerStage`
- `param $DisplaySpinnerStartedAt`
- `param $DisplaySpinnerStopEvent`
- `param $ForcePrepare`
- `param $Mode`
- `param $Port`
- `param $VarDir`

### `scripts/startup/presentation.ps1`
- `function Clear-WaitIndicatorLine`
- `function Complete-DisplayStage`
- `function Format-DisplayNameCell`
- `function Get-DisplayCellWidth`
- `function Get-RecoveryCommand`
- `function Get-WaitIndicatorLabel`
- `function Invoke-WaitIndicatorProcess`
- `function Read-StartupMenu`
- `function Select-StartupMode`
- `function Start-DisplayStage`
- `function Start-WaitIndicator`
- `function Stop-WaitIndicator`
- `function Write-Banner`
- `function Write-CliWelcome`
- `function Write-DisplayResult`
- `function Write-Startup`

### `scripts/startup/product.ps1`
- `function Get-StageFailureCode`
- `function Invoke-CliShell`
- `function Invoke-Package`
- `function Invoke-Python`
- `function Write-PythonEnvironment`
- `function Write-Stage`
- `function jiejian`
- `param $Value`

### `scripts/startup/runtime.ps1`
- `function Complete-PrepareDisplayTask`
- `function Fail-Start`
- `function Get-StageDisplayName`
- `function Handle-PrepareStatus`
- `function Invoke-External`
- `function Set-PrepareDisplayTask`

### `scripts/startup/source.ps1`
- `function Confirm-SourceFrontend`
- `function Get-SourceReceiptPath`
- `function Import-SourceReceipt`
- `function Invoke-SourcePreparation`
- `function Prepare-SourceRuntime`
- `function Test-ExactPath`

<!-- GENERATED:END -->
