# 界鉴开发总控台公开命令组合：启动、测试、Schema、Docs、CLI、Shell 与前端测试。

function Invoke-DevelopmentStart {
    if ($CommandArguments.Count -gt 0) { Fail-Development "start" "dev.ps1 start 不接受额外参数" "直接调用 scripts/start.ps1 并传入受支持的产品启动参数" }
    $shellName = if ($PSEdition -eq "Core") { "pwsh.exe" } else { "powershell.exe" }
    $shell = Join-Path $PSHOME $shellName
    if (-not (Test-Path -LiteralPath $shell -PathType Leaf)) { Fail-Development "start" "无法定位当前 PowerShell 产品启动入口" "修复 PowerShell 后直接运行 start.cmd" }
    $arguments = @("-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $script:ProjectRoot "scripts\start.ps1"), "-Mode", "Gui", "-VarDir", $script:VarDir)
    if ($ForcePrepare) { $arguments += "-ForcePrepare" }
    & $shell @arguments | Out-Host
    return [int]$LASTEXITCODE
}

function Invoke-DevelopmentTest {
    Exit-PrepareLock
    $testRoot = Join-Path $script:VarDir "test"
    New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
    $baseTemp = Join-Path $testRoot ("dev-{0}" -f [guid]::NewGuid().ToString("N"))
    try { Invoke-External "pytest" (@($script:Python, "-B", "-m", "pytest", "-p", "no:cacheprovider", "--basetemp", $baseTemp) + $CommandArguments) }
    finally { Remove-Item -LiteralPath $baseTemp -Recurse -Force -ErrorAction SilentlyContinue }
}

function Invoke-Schema {
    Exit-PrepareLock
    if ($CommandArguments.Count -gt 0) { Fail-Development "schema" "dev.ps1 schema 不接受位置参数" "使用 .\scripts\dev.ps1 schema 或追加 -Update" }
    $arguments = @($script:Python, "-B", "-m", "product.protocols.schema")
    if ($Update) { $arguments += "--update" }
    Invoke-External "schema" $arguments
}

function Invoke-Docs {
    if ($CommandArguments.Count -gt 0) { Fail-Development "docs" "dev.ps1 docs 不接受位置参数" "使用 .\scripts\dev.ps1 docs 或追加 -Update" }
    $docsPython = Resolve-DocsPython
    $arguments = @($docsPython, "-B", (Join-Path $script:ProjectRoot "scripts\docs\generate.py"), "--root", $script:ProjectRoot)
    if ($Update) { $arguments += "--update" }
    Invoke-External "docs" $arguments
    if ($Update) {
        # 更新后立即用只读模式复核生成区、llms 路由和 Markdown 内部链接。
        Invoke-External "docs-check" @($docsPython, "-B", (Join-Path $script:ProjectRoot "scripts\docs\generate.py"), "--root", $script:ProjectRoot)
    }
}

function Invoke-FrontendTest($Toolchain) {
    Remove-LegacyFrontendArtifacts
    $inputs = @(Get-FrontendSourceInputs)
    $dependencyDigest = Get-FrontendDependencyDigest $Toolchain
    Prepare-FrontendWorkspace $Toolchain $inputs $dependencyDigest
    $workspace = Get-FrontendWorkspace
    Invoke-External "frontend-editor" @($script:Node, (Join-Path $script:ProjectRoot "scripts\editor\verify-controlled-workspace-resolver.cjs"), $workspace, $script:ProjectRoot, $script:VarDir)
    Push-Location -LiteralPath $workspace
    try {
        $env:JIEJIAN_FRONTEND_CACHE_DIR = [IO.Path]::GetFullPath((Join-Path $script:DevelopmentRoot "cache\vite"))
        Invoke-External "frontend-test" (@($script:PnpmRunner + @("test")) + $CommandArguments)
    } finally { Pop-Location }
}

function Invoke-DevelopmentCli {
    Exit-PrepareLock
    Invoke-External "cli" (@($script:Python, "-B", "-m", "product.backend.cli", "--var-dir", $script:VarDir) + $CommandArguments)
}

function Invoke-DevelopmentShell {
    Exit-PrepareLock
    $shell = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) { "pwsh.exe" } else { "powershell.exe" }
    $python = $script:Python.Replace("'", "''")
    $project = $script:ProjectRoot.Replace("'", "''")
    $var = $script:VarDir.Replace("'", "''")
    $child = @"
function jiejian {
    param([Parameter(ValueFromRemainingArguments=`$true)][object[]]`$Arguments)
    & '$python' -B -m product.backend.cli --var-dir '$var' @Arguments
}
function quit { exit }
Set-Location -LiteralPath '$project'
Write-Host '界鉴命令以 jiejian 开头。' -ForegroundColor Cyan
Write-Host '输入 jiejian --help 查看命令。' -ForegroundColor Cyan
Write-Host '输入 exit 退出命令行；也可以输入 quit。' -ForegroundColor Cyan
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($child))
    & $shell -NoLogo -NoProfile -NoExit -EncodedCommand $encoded
}
