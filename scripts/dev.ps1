#Requires -Version 5.1
# 开发任务入口：装配工程模块、调度命令并恢复调用者环境。

[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet("bootstrap", "sync", "update", "prepare", "start", "cli", "test", "frontend-test", "sample-test", "verify", "schema", "docs", "shell", "package")]
    [string]$Command = "start",
    [string]$VarDir = "",
    [switch]$ForcePrepare,
    [switch]$Update,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommandArguments = @()
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "lib/session.ps1")
. (Join-Path $PSScriptRoot "lib/files.ps1")
. (Join-Path $PSScriptRoot "dev/context.ps1")
Initialize-DevelopmentContext (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path $VarDir

# 入口统一装配工程模块；共用库不依赖任务调度或产品业务。
. (Join-Path $PSScriptRoot "dev\common.ps1")
. (Join-Path $PSScriptRoot "dev\python.ps1")
. (Join-Path $PSScriptRoot "dev/node.ps1")
. (Join-Path $PSScriptRoot "editor/workspace.ps1")
. (Join-Path $PSScriptRoot "dev/frontend-workspace.ps1")
. (Join-Path $PSScriptRoot "dev/frontend.ps1")
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
    if ($CommandArguments.Count -gt 0 -and $Command -notin @("update", "cli", "test", "frontend-test", "sample-test", "verify")) {
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
        "verify" { Invoke-Verification }
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
