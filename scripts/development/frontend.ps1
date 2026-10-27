# 按输入身份构建前端，发布可复用产物并登记当前实例回执。

function Get-FrontendBuildDigest($Inputs, [string]$DependencyDigest) {
    $lines = New-Object System.Collections.Generic.List[string]
    $null = $lines.Add(("dependency|{0}" -f $DependencyDigest))
    foreach ($input in $Inputs) {
        $null = $lines.Add(("{0}|{1}" -f [string]$input.relative, (Get-FileDigest ([string]$input.source))))
    }
    $bytes = $script:Utf8NoBom.GetBytes(($lines -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToLowerInvariant() } finally { $sha.Dispose() }
}

function Invoke-FrontendBuild([string]$Workspace, [string]$Dist) {
    Push-Location -LiteralPath $Workspace
    try {
        $env:JIEJIAN_FRONTEND_OUT_DIR = [IO.Path]::GetFullPath($Dist)
        $env:JIEJIAN_FRONTEND_CACHE_DIR = [IO.Path]::GetFullPath((Join-Path $script:DevelopmentRoot "cache\vite"))
        # 构建诊断必须立即显示，不能被上层接收 build receipt 的赋值吞掉。
        Invoke-External "frontend-build" @($script:PnpmRunner + @("build")) | Out-Host
    } finally { Pop-Location }
}

function Get-FrontendBuildRoot([string]$BuildDigest) { return Join-Path $script:DevelopmentRoot ("frontend\builds\{0}" -f $BuildDigest) }

function Read-FrontendBuildReceipt([string]$BuildRoot) {
    $path = Join-Path $BuildRoot "receipt.json"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return $null }
    try { return Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json } catch { return $null }
}

function Test-FrontendBuild([string]$BuildRoot, [string]$BuildDigest, [string]$DependencyDigest) {
    $record = Read-FrontendBuildReceipt $BuildRoot
    return $null -ne $record -and [string]$record.build_digest -eq $BuildDigest -and [string]$record.dependency_digest -eq $DependencyDigest -and (Test-Path -LiteralPath (Join-Path $BuildRoot "dist\index.html") -PathType Leaf)
}

function Publish-FrontendBuild([string]$Workspace, [string]$BuildDigest, [string]$DependencyDigest) {
    $buildRoot = Get-FrontendBuildRoot $BuildDigest
    $temporary = Join-Path $script:DevelopmentRoot ("temp\frontend-build-{0}" -f [guid]::NewGuid().ToString("N"))
    $temporaryDist = Join-Path $temporary "dist"
    New-Item -ItemType Directory -Path $temporary -Force | Out-Null
    Register-StartupTemporary $temporary
    try {
        Invoke-FrontendBuild $Workspace $temporaryDist
        if (-not (Test-Path -LiteralPath (Join-Path $temporaryDist "index.html") -PathType Leaf)) { Fail-Development "frontend-build" "前端构建没有生成共享 build 的 index.html" "检查 TypeScript/Vite 输出" }
        $record = [ordered]@{
            schema_version = "1"; dependency_digest = $DependencyDigest; build_digest = $BuildDigest
            node_executable = $script:Node; node_version = $script:NodeVersion
            pnpm_executable = $script:PnpmRunner[1]; pnpm_version = $script:PnpmVersion
        }
        [IO.File]::WriteAllText((Join-Path $temporary "receipt.json"), ($record | ConvertTo-Json -Compress), $script:Utf8NoBom)
        New-Item -ItemType Directory -Path (Split-Path -Parent $buildRoot) -Force | Out-Null
        if (Test-Path -LiteralPath $buildRoot) { Remove-Item -LiteralPath $buildRoot -Recurse -Force }
        [IO.Directory]::Move($temporary, $buildRoot)
    } finally { Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue }
    return Read-FrontendBuildReceipt $buildRoot
}

function Copy-FrontendBuildToInstance([string]$BuildRoot, [string]$BuildDigest, [string]$DependencyDigest, $Record) {
    $source = Join-Path $BuildRoot "dist"
    $dist = Join-Path $script:VarDir "runtime\frontend"
    $temporary = Join-Path $script:VarDir ("runtime\frontend-{0}.tmp" -f [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path (Split-Path -Parent $temporary) -Force | Out-Null
    try {
        Copy-Item -LiteralPath $source -Destination $temporary -Recurse -Force
        if (-not (Test-Path -LiteralPath (Join-Path $temporary "index.html") -PathType Leaf)) { Fail-Development "frontend-build" "共享前端 build 副本缺少 index.html" "删除对应 var/development/frontend/builds 后重试" }
        if (Test-Path -LiteralPath $dist) { Remove-Item -LiteralPath $dist -Recurse -Force }
        [IO.Directory]::Move($temporary, $dist)
    } finally { Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue }
    $instanceReceipt = Join-Path $script:VarDir "runtime\build\frontend-receipt.json"
    $instanceTemporary = "$instanceReceipt.$([guid]::NewGuid().ToString('N')).tmp"
    $payload = [ordered]@{
        schema_version = "1"; dependency_digest = $DependencyDigest; build_digest = $BuildDigest
        shared_build = [IO.Path]::GetFullPath($BuildRoot); dist = [IO.Path]::GetFullPath($dist)
        node_executable = [string]$Record.node_executable; node_version = [string]$Record.node_version
        pnpm_executable = [string]$Record.pnpm_executable; pnpm_version = [string]$Record.pnpm_version
    }
    New-Item -ItemType Directory -Path (Split-Path -Parent $instanceReceipt) -Force | Out-Null
    try {
        [IO.File]::WriteAllText($instanceTemporary, ($payload | ConvertTo-Json -Compress), $script:Utf8NoBom)
        if (Test-Path -LiteralPath $instanceReceipt -PathType Leaf) { Remove-Item -LiteralPath $instanceReceipt -Force }
        [IO.File]::Move($instanceTemporary, $instanceReceipt)
    } finally { Remove-Item -LiteralPath $instanceTemporary -Force -ErrorAction SilentlyContinue }
    return $dist
}

function Set-FrontendToolEnvironment($Record) {
    if ($null -eq $Record) { return }
    $script:Node = [string]$Record.node_executable
    $script:NodeVersion = [string]$Record.node_version
    $script:PnpmVersion = [string]$Record.pnpm_version
    if (-not [string]::IsNullOrWhiteSpace([string]$Record.pnpm_executable)) { $script:PnpmRunner = @([string]$Record.node_executable, [string]$Record.pnpm_executable) }
    if (-not [string]::IsNullOrWhiteSpace($script:Node)) { $env:JIEJIAN_NODE_EXECUTABLE = $script:Node; $env:JIEJIAN_NODE_VERSION = $script:NodeVersion }
    if (-not [string]::IsNullOrWhiteSpace([string]$Record.pnpm_executable)) { $env:JIEJIAN_PNPM_EXECUTABLE = [string]$Record.pnpm_executable; $env:JIEJIAN_PNPM_VERSION = $script:PnpmVersion }
}

function Prepare-SourceFrontend($Toolchain) {
    Remove-LegacyFrontendArtifacts
    $inputs = @(Get-FrontendSourceInputs)
    $dependencyDigest = Get-FrontendDependencyDigest $Toolchain
    $buildDigest = Get-FrontendBuildDigest $inputs $dependencyDigest
    $buildRoot = Get-FrontendBuildRoot $buildDigest
    $buildHit = -not $ForcePrepare -and (Test-FrontendBuild $buildRoot $buildDigest $dependencyDigest)
    Write-PrepareStatus "frontend-dependencies" "start"
    if ($buildHit) {
        $record = Read-FrontendBuildReceipt $buildRoot
        Set-FrontendToolEnvironment $record
    } else {
        # ForcePrepare 可重建 build，但依赖摘要未变且 workspace 健康时绝不重复 pnpm install。
        Prepare-FrontendWorkspace $Toolchain $inputs $dependencyDigest
        $record = $null
    }
    Write-PrepareStatus "frontend-dependencies" "done"
    Write-PrepareStatus "frontend-build" "start"
    if (-not $buildHit) { $record = Publish-FrontendBuild (Get-FrontendWorkspace) $buildDigest $dependencyDigest }
    $dist = Copy-FrontendBuildToInstance $buildRoot $buildDigest $dependencyDigest $record
    $script:FrontendBuildState = if ($buildHit) { "reused" } else { "rebuilt" }
    $env:JIEJIAN_FRONTEND_DEPENDENCIES = if ($buildHit) { "共享依赖与 build 摘要命中，运行阶段无需 Node/pnpm" } else { "pnpm $($script:PnpmVersion) · 依赖工作区已复用或更新并完成构建" }
    $env:JIEJIAN_FRONTEND_DIST = [IO.Path]::GetFullPath($dist)
    $env:JIEJIAN_FRONTEND_BUILD_STATE = $script:FrontendBuildState
    Write-PrepareStatus "frontend-build" "done"
    if ($buildHit) { Write-Host ("复用共享前端 build：{0}" -f $buildDigest) -ForegroundColor DarkGray }
}
