#Requires -Version 5.1
# 自动 L5 命令入口：创建独立运行目录并调用 Python Harness，不替 start.cmd 完成产品准备。

function Invoke-SampleTest {
    if ($CommandArguments.Count -gt 0) {
        Fail-Development "sample-test" "dev.ps1 sample-test 不接受位置参数" "直接运行 .\scripts\dev.ps1 sample-test"
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
        $runRoot
    )
}
