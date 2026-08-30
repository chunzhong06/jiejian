#Requires -Version 5.1
# 自动 L5 命令入口：创建独立运行目录并调用 Python Harness，不替 start.cmd 完成产品准备。

function Invoke-SampleTest($Toolchain) {
    $suite = "official"
    if ($CommandArguments.Count -gt 1) {
        Fail-Development "sample-test" "sample-test 最多接受一个 suite" "使用 .\scripts\dev.ps1 sample-test [official|validation|competition|all]"
    }
    if ($CommandArguments.Count -eq 1) {
        $suite = [string]$CommandArguments[0]
    }
    if ($suite -notin @("official", "validation", "competition", "all")) {
        Fail-Development "sample-test" ("未知 suite：{0}" -f $suite) "使用 official、validation、competition 或 all"
    }
    if ($suite -ne "official") {
        # validation fixture 使用仓库受控的固定 Node，不依赖用户 PATH 中的偶然版本。
        Resolve-DevelopmentNode $Toolchain $true
    }
    Exit-PrepareLock
    $runRoot = Join-Path $script:VarDir ("test\sample-test\{0}" -f [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $runRoot -Force | Out-Null
    Invoke-External "sample-test" @(
        $script:Python,
        "-B",
        (Join-Path $script:ProjectRoot "scripts\dev\sample_test.py"),
        "--root",
        $script:ProjectRoot,
        "--var-dir",
        $runRoot,
        "--suite",
        $suite
    )
}
