#Requires -Version 5.1
# =============================================================================
# 界鉴仓库开发入口
#
# 定位
#   全局项目专用 Conda 环境、冻结 uv 依赖与仓库源码之间的唯一开发编排入口
#
# 职责
#   参数合同｜模块装配｜公开命令分派｜调用者环境快照与恢复
#
# 边界
#   具体 Python、前端、准备、打包、自动 L5 和命令实现分别归属 scripts/dev 职责模块。
# =============================================================================

[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet("bootstrap", "sync", "update", "prepare", "start", "cli", "test", "frontend-test", "sample-test", "schema", "docs", "shell", "package")]
    [string]$Command = "start",
    [string]$VarDir = "",
    [switch]$ForcePrepare,
    [switch]$Update,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments = @()
)

$ErrorActionPreference = "Stop"
$script:ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$script:VarDir = if ([string]::IsNullOrWhiteSpace($VarDir)) { Join-Path $script:ProjectRoot "var" } elseif ([IO.Path]::IsPathRooted($VarDir)) { [IO.Path]::GetFullPath($VarDir) } else { [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot $VarDir)) }
# 每轮产品事实由 -VarDir 隔离；跨实例共享的开发工具、构建与状态只进入固定 DevelopmentRoot。
$script:DevelopmentRoot = [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot "var\development"))
$script:ToolchainPath = Join-Path $script:ProjectRoot "product\config\toolchain.json"
$script:EnvironmentPath = Join-Path $script:ProjectRoot "environment.yml"
$script:StatePath = Join-Path $script:DevelopmentRoot "state\development-state.json"
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$script:PrepareLock = $null
$script:Python = $null
$script:Conda = $null
$script:CondaPrefix = $null
$script:Uv = $null
$script:UvVersion = $null
$script:Node = $null
$script:NodeVersion = $null
$script:PnpmRunner = @()
$script:PnpmVersion = $null
$script:FrontendBuildState = $null
$script:State = [pscustomobject]@{ schema_version = "1" }
$script:CallerEnvironmentSnapshot = $null

# 只有总控入口装配模块；子模块共享本作用域的简单 $script: 状态，不互相加载。
. (Join-Path $PSScriptRoot "dev\common.ps1")
. (Join-Path $PSScriptRoot "dev\python.ps1")
. (Join-Path $PSScriptRoot "dev\frontend.ps1")
. (Join-Path $PSScriptRoot "dev\prepare.ps1")
. (Join-Path $PSScriptRoot "dev\package.ps1")
. (Join-Path $PSScriptRoot "dev\sample-test.ps1")
. (Join-Path $PSScriptRoot "dev\commands.ps1")

function Test-CommandContract {
    if ($Update -and $Command -notin @("schema", "docs")) {
        Fail-Development "arguments" "-Update 只允许与 schema 或 docs 命令一起使用" "使用 .\scripts\dev.ps1 schema -Update 或 .\scripts\dev.ps1 docs -Update"
    }
    if ($ForcePrepare -and $Command -notin @("prepare", "start", "package")) {
        Fail-Development "arguments" "-ForcePrepare 只允许与 prepare、start 或 package 命令一起使用" "调整命令参数后重试"
    }
    if ($CommandArguments.Count -gt 0 -and $Command -notin @("update", "cli", "test", "frontend-test", "sample-test")) {
        Fail-Development "arguments" ("{0} 命令不接受位置参数" -f $Command) "只为 update、cli、test、frontend-test 或 sample-test 传递位置参数"
    }
}

try {
    Save-CallerEnvironment
    [Console]::InputEncoding = $script:Utf8NoBom
    [Console]::OutputEncoding = $script:Utf8NoBom
    $OutputEncoding = $script:Utf8NoBom
    Test-CommandContract
    if ($Command -eq "start") {
        exit (Invoke-DevelopmentStart)
    }
    Enter-PrepareLock
    Read-State
    if ($Command -eq "update") {
        Invoke-Update
        Write-Host "uv.lock 与 jiejian_env 已更新。" -ForegroundColor Green
        exit 0
    }
    if ($Command -eq "docs") {
        Invoke-Docs
        exit 0
    }
    $mode = if ($Command -eq "bootstrap") { "bootstrap" } elseif ($Command -eq "sync") { "sync" } else { "auto" }
    $toolchain = Prepare-Python $mode
    switch ($Command) {
        "bootstrap" { Write-Host "jiejian_env 已按 environment.yml 与 uv.lock 完整准备。" -ForegroundColor Green }
        "sync" { Write-Host "jiejian_env 已按 uv.lock 精确同步。" -ForegroundColor Green }
        "prepare" { Prepare-SourceRuntime $toolchain }
        "cli" { Invoke-DevelopmentCli }
        "test" { Invoke-DevelopmentTest }
        "frontend-test" { Invoke-FrontendTest $toolchain }
        "sample-test" { Invoke-SampleTest $toolchain }
        "schema" { Invoke-Schema }
        "shell" { Invoke-DevelopmentShell }
        "package" { Invoke-Package $toolchain }
    }
} catch {
    if ($_.Exception.Message) { Write-Host $_.Exception.Message -ForegroundColor Red }
    exit 1
} finally {
    try { Restore-CallerEnvironment }
    finally { Exit-PrepareLock }
}
