# 产品准备：数据库迁移、前端构建及启动阶段编排。
# 每个缓存命中必须同时满足输入指纹和可观察产物事实。
function Get-DatabaseRevision([string]$DatabasePath) {
    if (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) { return "missing" }
    $code = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print((c.execute('select version_num from alembic_version').fetchone() or ['missing'])[0]); c.close()"
    Start-WaitIndicator "database-check"
    try {
        $result = (& $script:PythonRunner[0] @($script:PythonRunner[1..($script:PythonRunner.Count - 1)] + @("-c", $code, $DatabasePath)) 2>$null | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($result)) { return "unknown" }
        return $result.Split("`n")[-1].Trim()
    } catch { return "unknown" }
    finally { Stop-WaitIndicator }
}

function Prepare-Migration {
    $database = Join-Path $script:VarDir "jiejian.db"
    $migrationFiles = @((Join-Path $script:ProjectRoot "product\backend\alembic.ini"), (Join-Path $script:ProjectRoot "product\backend\migrations"))
    $fingerprint = Get-StageFingerprint $migrationFiles @{ database_path = [IO.Path]::GetFullPath($database) }
    $entry = Get-PhaseState "migration"
    $current = Get-DatabaseRevision $database
    $validCurrent = -not [string]::IsNullOrWhiteSpace([string]$current) -and $current -notin @("missing", "unknown")
    # 指纹命中不足以证明数据库可用，仍需核对实际文件和当前 revision。
    if ((Test-PhaseHit "migration" $fingerprint) -and $validCurrent -and (Test-Path -LiteralPath $database -PathType Leaf) -and $null -ne $entry.facts -and $entry.facts.revision -eq $current) {
        Write-Startup "[migration] 跳过：指纹命中且数据库 revision=$current"
        $script:MigrationDetail = "修订 $current · 已是最新"
        return
    }
    Invoke-Python @("-c", "import sys; from pathlib import Path; from product.backend.infra.storage import default_database_path, upgrade_database; upgrade_database(default_database_path(Path(sys.argv[1])))", $script:VarDir) "migration" 43
    $revision = Get-DatabaseRevision $database
    if ([string]::IsNullOrWhiteSpace([string]$revision) -or $revision -in @("missing", "unknown")) {
        Fail-Start 43 "migration" "迁移完成后未能读取有效 Alembic revision" (Get-RecoveryCommand)
    }
    Set-PhaseState "migration" $fingerprint @{ database_path = [IO.Path]::GetFullPath($database); revision = $revision }
    $script:MigrationDetail = "修订 $revision · 已更新"
}

function Prepare-Frontend {
    if ($null -eq $script:PnpmRunner -or $script:PnpmRunner.Count -lt 1) {
        Fail-Start 31 "pnpm" "前端构建缺少已确认的 pnpm runner" (Get-RecoveryCommand)
    }
    $pnpm = @($script:PnpmRunner)
    $frontend = Join-Path $script:ProjectRoot "product\frontend"
    $nodeFiles = @((Join-Path $frontend "package.json"), (Join-Path $frontend "pnpm-lock.yaml"), (Join-Path $frontend "pnpm-workspace.yaml"))
    $nodeFingerprint = Get-StageFingerprint $nodeFiles @{ node_version = $script:NodeVersion; pnpm_version = $script:PnpmVersion }
    $script:NodeDependenciesFingerprint = $nodeFingerprint
    $nodeModules = Join-Path $frontend "node_modules"
    $pnpmStoreRoot = Get-PnpmStoreRoot
    $expectedStoreDir = Get-ExpectedPnpmStoreDir
    $expectedVirtualStoreDir = Get-ExpectedPnpmVirtualStoreDir
    $requiredNodeEntries = @(
        (Join-Path $nodeModules ".modules.yaml"),
        (Join-Path $nodeModules ".bin\tsc.cmd"),
        (Join-Path $nodeModules ".bin\vite.cmd")
    )
    # 内容寻址缓存位于 VarDir；已安装依赖保留 pnpm 默认布局，保证工具链按标准祖先链解析类型。
    $nodeDependenciesHealthy = (Test-Path -LiteralPath $nodeModules -PathType Container) -and
        (Test-Path -LiteralPath $expectedStoreDir -PathType Container) -and
        (Test-Path -LiteralPath $expectedVirtualStoreDir -PathType Container) -and
        -not ($requiredNodeEntries | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) }) -and
        (Test-PnpmLayout (Join-Path $nodeModules ".modules.yaml") $expectedStoreDir $expectedVirtualStoreDir)
    $nodeDependenciesRebuilt = $false
    $nodeState = Get-PhaseState "node_dependencies"
    $nodeStateHit = Test-PhaseHit "node_dependencies" $nodeFingerprint
    $nodeInstallNeeded = (-not $nodeDependenciesHealthy) -or ($null -ne $nodeState -and -not $nodeStateHit)
    if ($nodeInstallNeeded) {
        if (-not $nodeDependenciesHealthy) {
            $expectedNodeModules = [IO.Path]::GetFullPath((Join-Path $frontend "node_modules"))
            if ([IO.Path]::GetFullPath($nodeModules) -ne $expectedNodeModules) {
                Fail-Start 44 "frontend-install" "拒绝清理无法确认的前端依赖目录" (Get-RecoveryCommand)
            }
            Write-Startup "[node_dependencies] 检测到依赖入口残缺，重建 node_modules"
            try {
                $entry = Get-Item -LiteralPath $nodeModules -Force -ErrorAction SilentlyContinue
                if ($null -ne $entry) {
                    if ($entry.LinkType -in @("Junction", "SymbolicLink")) {
                        Remove-Item -LiteralPath $nodeModules -Force -ErrorAction Stop
                    } else {
                        Remove-Item -LiteralPath $nodeModules -Recurse -Force -ErrorAction Stop
                    }
                }
            } catch {
                Fail-Start 44 "frontend-install" "无法清理损坏的 node_modules：$($_.Exception.Message)" (Get-RecoveryCommand)
            }
        }
        Push-Location -LiteralPath $frontend
        try { Invoke-External "frontend-install" $pnpm @("install", "--store-dir", $pnpmStoreRoot, "--virtual-store-dir", $expectedVirtualStoreDir, "--frozen-lockfile") 44 } finally { Pop-Location }
        if (($requiredNodeEntries | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) }) -or
            -not (Test-PnpmLayout (Join-Path $nodeModules ".modules.yaml") $expectedStoreDir $expectedVirtualStoreDir)) {
            Fail-Start 44 "frontend-install" "依赖安装完成，但 TypeScript/Vite 入口仍不完整" (Get-RecoveryCommand)
        }
        Set-PhaseState "node_dependencies" $nodeFingerprint @{ node_version = $script:NodeVersion; pnpm_version = $script:PnpmVersion; store_root = $pnpmStoreRoot; store_dir = $expectedStoreDir; virtual_store_dir = $expectedVirtualStoreDir }
        $nodeDependenciesRebuilt = $true
        $script:FrontendDependenciesDetail = "pnpm $script:PnpmVersion · 已更新"
    } elseif (-not $nodeStateHit) {
        Write-Startup "[node_dependencies] 跳过：关键入口与 pnpm store 探针通过，重建准备状态"
        $script:FrontendDependenciesDetail = "pnpm $script:PnpmVersion · 已验证并复用"
        Set-PhaseState "node_dependencies" $nodeFingerprint @{ node_version = $script:NodeVersion; pnpm_version = $script:PnpmVersion; store_root = $pnpmStoreRoot; store_dir = $expectedStoreDir; virtual_store_dir = $expectedVirtualStoreDir }
    } else { Write-Startup "[node_dependencies] 跳过：指纹命中且关键依赖入口可用"; $script:FrontendDependenciesDetail = "pnpm $script:PnpmVersion · 已复用" }
    $buildFiles = @((Join-Path $frontend "src"), (Join-Path $frontend "index.html"), (Join-Path $frontend "package.json"), (Join-Path $frontend "pnpm-lock.yaml")) + @(Get-ChildItem -LiteralPath $frontend -File | Where-Object { $_.Name -like "tsconfig*.json" -or $_.Name -like "vite.config.*" } | Select-Object -ExpandProperty FullName)
    $buildFingerprint = Get-StageFingerprint $buildFiles @{ node_dependencies = $nodeFingerprint }
    $index = Join-Path $frontend "dist\index.html"
    if ($nodeDependenciesRebuilt -or -not (Test-PhaseHit "frontend_build" $buildFingerprint) -or -not (Test-Path -LiteralPath $index -PathType Leaf)) {
        Push-Location -LiteralPath $frontend
        try { Invoke-External "frontend-build" @($pnpm) @("build") 44 } finally { Pop-Location }
        if (-not (Test-Path -LiteralPath $index -PathType Leaf)) { Fail-Start 44 "frontend-build" "构建未生成 dist/index.html" (Get-RecoveryCommand) }
        Set-PhaseState "frontend_build" $buildFingerprint @{ node_dependencies = $nodeFingerprint }
        $script:FrontendBuildDetail = "已更新"
    } else { Write-Startup "[frontend_build] 跳过：指纹命中且 dist/index.html 存在"; $script:FrontendBuildDetail = "已复用" }
}

function Write-PythonEnvironment {
    Write-Startup ("Python 环境: {0}`nPython 环境路径: {1}`nPython 可执行文件: {2}" -f $script:PythonEnvironmentType, $script:PythonEnvironmentPath, $script:PythonExecutable)
    if ($null -ne $script:PythonEnvironmentReport) {
        $siteStatus = if ($script:PythonEnvironmentReport.user_site_on_sys_path) { "检测到用户级来源" } else { "未使用用户级来源" }
        Write-Startup ("Python site-packages: {0}`n依赖来源: {1}" -f $siteStatus, ($script:PythonEnvironmentReport.package_origins | ConvertTo-Json -Compress))
    }
    Write-Startup "后续 CLI 用法: <已解析 Python> -B -m product.backend.cli <命令>"
}

function Write-RuntimeSummary {
    Write-Host ""
    Write-Host "当前界鉴运行环境" -ForegroundColor Cyan
    Write-Host ("  Python    {0}  {1}" -f $script:PythonVersion, $script:PythonExecutable) -ForegroundColor Gray
    Write-Host ("  环境来源  {0}  {1}" -f $script:PythonEnvironmentType, $script:PythonEnvironmentPath) -ForegroundColor Gray
    Write-Host ("  用户级包  {0}" -f ($(if ($script:PythonEnvironmentReport.user_site_on_sys_path) { "检测到" } else { "未使用" }))) -ForegroundColor Gray
    Write-Host ("  Node.js   {0}  {1}" -f $script:NodeVersion, $script:NodeExecutable) -ForegroundColor Gray
    Write-Host ("  pnpm      {0}  {1}" -f $script:PnpmVersion, $script:PnpmExecutable) -ForegroundColor Gray
    Write-Host ("  Chromium  {0}" -f $script:ChromiumExecutable) -ForegroundColor Gray
}

function Invoke-Python([object[]]$Arguments, [string]$Stage, [int]$Code = 40) {
    Invoke-External $Stage $script:PythonRunner $Arguments $Code
}

function Invoke-Package([object[]]$Arguments, [string]$Stage, [int]$Code = 50) {
    Invoke-External $Stage $script:PackageRunner $Arguments $Code
}

function Invoke-CliShell([bool]$StartGuide = $false) {
    # 子 shell 只继承本轮已确认的绝对 Python、项目、VarDir 和工具 PATH，不写用户配置。

    if (-not $StartGuide) { Write-CliWelcome }
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
    $guideLiteral = if ($StartGuide) { '$true' } else { '$false' }
    $childScript = @"
`$projectRoot = $projectLiteral
`$varDir = $varLiteral
`$startGuide = $guideLiteral
function jiejian {
    param([Parameter(ValueFromRemainingArguments=`$true)][object[]]`$CommandArgs)
    & $pythonLiteral -B -m product.backend.cli --var-dir `$varDir @(`$CommandArgs)
}
Set-Location -LiteralPath `$projectRoot
if (`$startGuide) {
    `$env:JIEJIAN_GUIDE_STARTUP = "1"
    try { jiejian --human guide } finally { Remove-Item Env:JIEJIAN_GUIDE_STARTUP -ErrorAction SilentlyContinue }
    if (`$LASTEXITCODE -eq 10) { exit 0 }
    Write-Host ""
    Write-Host "已进入普通命令行" -ForegroundColor Cyan
    Write-Host "输入 jiejian --help 查看完整命令。" -ForegroundColor DarkGray
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
