#Requires -Version 5.1

# 图形 Sample 薄入口：启动受控 Target 后转交正常 start.cmd，并在退出时清理。
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
    Write-Host ("执行配置：{0}" -f $target.Profile) -ForegroundColor Gray
    Write-Host ("权限契约：{0}" -f $target.Contract) -ForegroundColor Gray
    Write-Host "界鉴将通过正常图形界面启动；请使用上面的公开配置完成应用接入。" -ForegroundColor Cyan
    & $context.StartCommand -Mode Gui -VarDir $context.VarDir
    $exitCode = $LASTEXITCODE
} finally {
    if ($null -ne $target) { Stop-SampleTarget $target }
    Restore-SampleSecrets $savedSecrets
}
exit $exitCode
