# =============================================================================
# 产品进程启动
#
# 定位
#   已确认源码运行环境与 CLI/GUI 产品入口之间的薄编排层
#
# 职责
#   展示环境事实｜调用统一产品 CLI｜创建仅对当前会话生效的命令行入口
#
# 边界
#   不准备依赖、数据库或前端，不复制 ApplicationCore 业务流程。
# =============================================================================

function Write-PythonEnvironment {
    Write-Startup ("Python 环境: {0}`nPython 环境路径: {1}`nPython 可执行文件: {2}" -f $script:PythonEnvironmentType, $script:PythonEnvironmentPath, $script:PythonExecutable)
    if ($null -ne $script:PythonEnvironmentReport) {
        $siteStatus = if ($script:PythonEnvironmentReport.user_site_on_sys_path) { "检测到用户级来源" } else { "未使用用户级来源" }
        Write-Startup ("Python site-packages: {0}`n依赖来源: {1}" -f $siteStatus, ($script:PythonEnvironmentReport.package_origins | ConvertTo-Json -Compress))
    }
    Write-Startup "后续 CLI 用法: <已解析 Python> -B -m product.backend.cli <命令>"
}

function Invoke-Python([object[]]$Arguments, [string]$Stage, [int]$Code = 40) {
    Invoke-External $Stage $script:PythonRunner $Arguments $Code
}

function Invoke-Package([object[]]$Arguments, [string]$Stage, [int]$Code = 50) {
    Invoke-External $Stage $script:PackageRunner $Arguments $Code
}

function Invoke-CliShell([bool]$ShowStatus = $false) {
    # 子 shell 只继承本轮已确认的绝对 Python、项目和 VarDir，不写用户配置。
    if (-not $ShowStatus) { Write-CliWelcome }
    $shellName = if ($PSEdition -eq "Core") { "pwsh.exe" } else { "powershell.exe" }
    $shell = Join-Path $PSHOME $shellName
    if (-not (Test-Path -LiteralPath $shell -PathType Leaf)) {
        Fail-Start 50 "cli" "无法定位 PowerShell 子 shell" "确认 PowerShell 安装后重新执行本脚本"
    }
    $quote = {
        param([object]$Value)
        $escaped = ([string]$Value) -replace "'", "''"
        return "'$escaped'"
    }
    if ([string]::IsNullOrWhiteSpace([string]$script:PythonExecutable) -or -not (Test-Path -LiteralPath $script:PythonExecutable -PathType Leaf)) {
        Fail-Start 50 "cli" "无法定位已解析的 Python 可执行文件" "重新执行准备阶段后重试"
    }
    $pythonLiteral = & $quote $script:PythonExecutable
    $projectLiteral = & $quote $script:ProjectRoot
    $varLiteral = & $quote $script:VarDir
    $statusLiteral = if ($ShowStatus) { '$true' } else { '$false' }
    $childScript = @"
`$projectRoot = $projectLiteral
`$varDir = $varLiteral
`$showStatus = $statusLiteral
function jiejian {
    param([Parameter(ValueFromRemainingArguments=`$true)][object[]]`$CommandArgs)
    & $pythonLiteral -B -m product.backend.cli --var-dir `$varDir @(`$CommandArgs)
}
Set-Location -LiteralPath `$projectRoot
if (`$showStatus) {
    jiejian --human status
    Write-Host ""
    Write-Host "已进入普通命令行" -ForegroundColor Cyan
    Write-Host "输入 jiejian --help 查看命令。" -ForegroundColor DarkGray
}
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($childScript))
    try {
        & $shell -NoLogo -NoProfile -NoExit -EncodedCommand $encoded
        $code = $LASTEXITCODE
    } catch {
        Fail-Start 50 "cli" ("命令行子 shell 启动失败: " + $_.Exception.Message) (Get-RecoveryCommand)
    }
    if ($code -ne 0) {
        Fail-Start 50 "cli" ("命令行子 shell 返回 $code") (Get-RecoveryCommand)
    }
}

function Write-Stage([string]$Stage, [string]$Message) {
    Write-Startup (">>> [{0}] {1}" -f $Stage, $Message)
}

function Get-StageFailureCode([string]$Stage) {
    switch ($Stage) {
        "prepare-lock" { return 22 }
        "source-prepare" { return 40 }
        "conda" { return 20 }
        "uv" { return 21 }
        "lock" { return 22 }
        "node" { return 30 }
        "pnpm" { return 31 }
        "playwright" { return 41 }
        "doctor" { return 42 }
        "migration" { return 43 }
        "frontend-install" { return 44 }
        "frontend-build" { return 44 }
        "serve" { return 50 }
        default { return 40 }
    }
}
