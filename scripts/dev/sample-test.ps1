#Requires -Version 5.1
# 准备受控工具后显式运行独立官方示例，不读取用户应用。
function Invoke-SampleTest($Toolchain) {
    if ($CommandArguments.Count -gt 2 -or ($CommandArguments.Count -ge 1 -and $CommandArguments[0] -ne "official") -or ($CommandArguments.Count -eq 2 -and $CommandArguments[1] -notin @("baseline", "repair"))) {
        Fail-Development "sample-test" "运行验收范围应为 official baseline 或 official repair" "使用 scripts/dev.ps1 sample-test official；仅验证修复链时追加 repair"
    }
    Resolve-DevelopmentNode $Toolchain $true
    Prepare-Chromium
    Prepare-SourceFrontend $Toolchain
    $previousAcceptance = $env:JIEJIAN_RUNTIME_ACCEPTANCE
    $previousOutput = $env:JIEJIAN_ACCEPTANCE_OUTPUT
    $previousArguments = $script:CommandArguments
    $previousScope = $env:JIEJIAN_ACCEPTANCE_SCOPE
    $env:JIEJIAN_ACCEPTANCE_SCOPE = if ($CommandArguments.Count -eq 2) { $CommandArguments[1] } else { "baseline" }
    $env:JIEJIAN_RUNTIME_ACCEPTANCE = "1"
    $env:JIEJIAN_ACCEPTANCE_OUTPUT = Join-Path $script:VarDir ("audit/runtime-tests/{0}" -f [guid]::NewGuid().ToString("N"))
    $script:CommandArguments = @("tests/runtime", "-m", ("runtime and {0}" -f $env:JIEJIAN_ACCEPTANCE_SCOPE))
    try { Invoke-DevelopmentTest }
    finally {
        Write-Host ("运行验收结果：{0}" -f $env:JIEJIAN_ACCEPTANCE_OUTPUT)
        $script:CommandArguments = $previousArguments
        $env:JIEJIAN_RUNTIME_ACCEPTANCE = $previousAcceptance
        $env:JIEJIAN_ACCEPTANCE_OUTPUT = $previousOutput
        $env:JIEJIAN_ACCEPTANCE_SCOPE = $previousScope
    }
}
