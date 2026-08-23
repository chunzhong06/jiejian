#Requires -Version 5.1

# 命令行 Sample 薄入口：注入临时身份并调用公开 jiejian run，退出时清理 Target。
[CmdletBinding(PositionalBinding = $false)]
param(
    [ValidateSet("fixed", "vulnerable", "inconclusive")]
    [string]$Variant = "vulnerable",
    [string]$VarDir = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "_sample.ps1")

$context = Resolve-SampleContext $VarDir
$savedSecrets = Set-SampleSecrets
$target = $null
$exitCode = 1
try {
    $target = Start-SampleTarget $context $Variant
    Write-Host ("Sample Target：{0}" -f $target.Address) -ForegroundColor Cyan
    Write-Host ("正在通过公开命令运行：jiejian run {0}" -f $target.Profile) -ForegroundColor Cyan
    & $context.PowerShell -NoLogo -NoProfile -ExecutionPolicy Bypass -File $context.DevScript cli -VarDir $context.VarDir run $target.Profile
    $exitCode = $LASTEXITCODE
} finally {
    if ($null -ne $target) { Stop-SampleTarget $target }
    Restore-SampleSecrets $savedSecrets
}
exit $exitCode
