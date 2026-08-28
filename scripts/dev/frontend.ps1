# 界鉴开发总控台 Node、pnpm、前端受控工作区与构建回执职责。

function Resolve-DevelopmentNode($Toolchain, [bool]$Exact) {
    if ($Exact) {
        $architecture = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
        $key = switch ($architecture.ToUpperInvariant()) { "AMD64" { "x64" } "ARM64" { "arm64" } default { $null } }
        if ($null -eq $key) { Fail-Development "frontend" "当前 Windows 架构不受发布构建工具链支持" "使用 AMD64 或 ARM64 Windows" }
        $nodeVersion = [string]$Toolchain.node.build_version
        $pnpmVersion = [string]$Toolchain.pnpm.version
        $nodeRoot = Join-Path $script:DevelopmentRoot ("tools\node\{0}\{1}" -f $nodeVersion, $key)
        $nodeExecutable = Join-Path $nodeRoot ("node-v{0}-win-{1}\node.exe" -f $nodeVersion, $key)
        $pnpmRoot = Join-Path $script:DevelopmentRoot ("tools\pnpm\{0}" -f $pnpmVersion)
        $pnpmEntry = Join-Path $pnpmRoot "package\bin\pnpm.cjs"
        $receiptPath = Join-Path $script:DevelopmentRoot "state\toolchain-receipt.json"
        $hashProperty = "{0}_sha256" -f $key
        $expectedNodeHash = [string]$Toolchain.node.windows.PSObject.Properties[$hashProperty].Value
        $healthy = $false
        if ((Test-Path -LiteralPath $nodeExecutable -PathType Leaf) -and (Test-Path -LiteralPath $pnpmEntry -PathType Leaf) -and (Test-Path -LiteralPath $receiptPath -PathType Leaf)) {
            try {
                $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $healthy = $receipt.node_version -eq $nodeVersion -and $receipt.pnpm_version -eq $pnpmVersion -and $receipt.node_executable_sha256 -eq (Get-FileDigest $nodeExecutable) -and $receipt.pnpm_entry_sha256 -eq (Get-FileDigest $pnpmEntry)
            } catch { $healthy = $false }
        }
        if (-not $healthy) {
            $downloadRoot = Join-Path $script:DevelopmentRoot ("temp\build-toolchain-{0}" -f [guid]::NewGuid().ToString("N"))
            $nodeArchive = Join-Path $downloadRoot ("node-v{0}-win-{1}.zip" -f $nodeVersion, $key)
            $pnpmArchive = Join-Path $downloadRoot ("pnpm-{0}.tgz" -f $pnpmVersion)
            New-Item -ItemType Directory -Path $downloadRoot -Force | Out-Null
            try {
                Invoke-WebRequest -Uri ("{0}node-v{1}-win-{2}.zip" -f [string]$Toolchain.node.source, $nodeVersion, $key) -OutFile $nodeArchive -UseBasicParsing
                if ((Get-FileDigest $nodeArchive) -ne $expectedNodeHash) { Fail-Development "frontend" "Node.js 发布构建归档校验失败" "检查 product/config/toolchain.json 与官方下载源" }
                Invoke-WebRequest -Uri ([string]$Toolchain.pnpm.source) -OutFile $pnpmArchive -UseBasicParsing
                $sha512 = [Security.Cryptography.SHA512]::Create()
                try { $pnpmIntegrity = "sha512-" + [Convert]::ToBase64String($sha512.ComputeHash([IO.File]::ReadAllBytes($pnpmArchive))) } finally { $sha512.Dispose() }
                if ($pnpmIntegrity -ne [string]$Toolchain.pnpm.integrity) { Fail-Development "frontend" "pnpm 发布构建归档完整性校验失败" "检查 product/config/toolchain.json 与 npm 官方归档" }
                Remove-Item -LiteralPath $nodeRoot -Recurse -Force -ErrorAction SilentlyContinue
                Remove-Item -LiteralPath $pnpmRoot -Recurse -Force -ErrorAction SilentlyContinue
                New-Item -ItemType Directory -Path $nodeRoot -Force | Out-Null
                New-Item -ItemType Directory -Path $pnpmRoot -Force | Out-Null
                Expand-Archive -LiteralPath $nodeArchive -DestinationPath $nodeRoot -Force
                & tar.exe -xzf $pnpmArchive -C $pnpmRoot
                if ($LASTEXITCODE -ne 0) { Fail-Development "frontend" "无法展开固定 pnpm 归档" "确认 Windows tar.exe 可用后重试" }
                if (-not (Test-Path -LiteralPath $nodeExecutable -PathType Leaf) -or -not (Test-Path -LiteralPath $pnpmEntry -PathType Leaf)) { Fail-Development "frontend" "发布构建工具归档缺少预期入口" "删除 var/development/tools 中对应工具后重试" }
                $receipt = [ordered]@{ schema_version = "1"; node_version = $nodeVersion; pnpm_version = $pnpmVersion; node_archive_sha256 = $expectedNodeHash; pnpm_integrity = $pnpmIntegrity; node_executable_sha256 = Get-FileDigest $nodeExecutable; pnpm_entry_sha256 = Get-FileDigest $pnpmEntry }
                New-Item -ItemType Directory -Path (Split-Path -Parent $receiptPath) -Force | Out-Null
                [IO.File]::WriteAllText($receiptPath, ($receipt | ConvertTo-Json -Compress), $script:Utf8NoBom)
            } finally { Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue }
        }
        $script:Node = [IO.Path]::GetFullPath($nodeExecutable)
        $script:PnpmRunner = @($script:Node, [IO.Path]::GetFullPath($pnpmEntry))
        $script:NodeVersion = (& $script:Node --version 2>&1 | Out-String).Trim().TrimStart("v")
        $script:PnpmVersion = (& $script:PnpmRunner[0] $script:PnpmRunner[1] --version 2>&1 | Out-String).Trim()
        if ($script:NodeVersion -ne $nodeVersion -or $script:PnpmVersion -ne $pnpmVersion) { Fail-Development "frontend" "固定发布构建工具版本探针失败" "删除 var/development/tools 中对应工具后重新执行 package" }
        $originalPath = [string]$script:CallerEnvironmentSnapshot.variables["PATH"].value
        $env:PATH = (Split-Path -Parent $script:Node) + ";" + $originalPath
        $env:JIEJIAN_NODE_EXECUTABLE = $script:Node
        $env:JIEJIAN_NODE_VERSION = $script:NodeVersion
        $env:JIEJIAN_PNPM_EXECUTABLE = $script:PnpmRunner[1]
        $env:JIEJIAN_PNPM_VERSION = $script:PnpmVersion
        return
    }
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    $pnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $node -or $null -eq $pnpm) { Fail-Development "frontend" "开发前端需要 Node.js 与 pnpm" "安装满足 package.json 的 Node.js 和 pnpm，或执行发布构建准备" }
    $nodeVersion = (& $node.Source --version 2>&1 | Out-String).Trim().TrimStart("v")
    $pnpmVersion = (& $pnpm.Source --version 2>&1 | Out-String).Trim()
    try { $parsed = [version]$nodeVersion } catch { $parsed = $null }
    $nodeOk = $null -ne $parsed -and $parsed -ge [version]"24.13.0" -and $parsed.Major -lt 25
    if (-not $nodeOk -or $pnpmVersion -ne [string]$Toolchain.pnpm.version) { Fail-Development "frontend" "Node/pnpm 版本不符合工具链清单" ("需要 Node {0} 与 pnpm {1}" -f $Toolchain.node.development_range, $Toolchain.pnpm.version) }
    $script:Node = $node.Source
    $script:NodeVersion = $nodeVersion
    $script:PnpmRunner = @($pnpm.Source)
    $script:PnpmVersion = $pnpmVersion
    $env:JIEJIAN_NODE_EXECUTABLE = $script:Node
    $env:JIEJIAN_NODE_VERSION = $script:NodeVersion
    $env:JIEJIAN_PNPM_EXECUTABLE = $script:PnpmRunner[0]
    $env:JIEJIAN_PNPM_VERSION = $script:PnpmVersion
}

function Remove-LegacyFrontendArtifacts {
    $frontend = Join-Path $script:ProjectRoot "product\frontend"
    # 只删除旧设计明确生成的三类路径；未知文件属于用户工作树，准备入口不得猜测清理。
    foreach ($path in @((Join-Path $frontend "node_modules"), (Join-Path $frontend "dist"), (Join-Path $frontend "tsconfig.tsbuildinfo"))) { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction SilentlyContinue }
}

function Get-FrontendSourceInputs {
    $frontend = [IO.Path]::GetFullPath((Join-Path $script:ProjectRoot "product\frontend"))
    $prefix = $frontend.TrimEnd("\") + "\"
    $generatedDirectories = @("node_modules", "dist", "coverage", ".vite", ".cache")
    $directories = New-Object System.Collections.Generic.Stack[string]
    $inputs = New-Object System.Collections.Generic.List[object]
    $directories.Push($frontend)
    while ($directories.Count -gt 0) {
        $directory = $directories.Pop()
        foreach ($item in Get-ChildItem -LiteralPath $directory -Force) {
            if ($item.PSIsContainer) { if ($item.Name -notin $generatedDirectories) { $directories.Push($item.FullName) }; continue }
            if ($item.Name.EndsWith(".tsbuildinfo", [StringComparison]::OrdinalIgnoreCase)) { continue }
            $relative = $item.FullName.Substring($prefix.Length).Replace("\", "/")
            $null = $inputs.Add([pscustomobject]@{ source = [IO.Path]::GetFullPath($item.FullName); relative = $relative })
        }
    }
    return @($inputs | Sort-Object relative)
}

function Get-FrontendEditorPluginRoot { return Join-Path $script:ProjectRoot "scripts\editor\typescript-plugins\jiejian-controlled-workspace-resolver" }

function Get-FrontendDependencyDigest($Toolchain) {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($relative in @("package.json", "pnpm-lock.yaml")) {
        $path = Join-Path $script:ProjectRoot ("product\frontend\{0}" -f $relative)
        $null = $lines.Add(("{0}|{1}" -f $relative, (Get-FileDigest $path)))
    }
    $editorPlugin = Get-FrontendEditorPluginRoot
    $editorPrefix = $editorPlugin.TrimEnd("\") + "\"
    foreach ($file in Get-ChildItem -LiteralPath $editorPlugin -File -Recurse | Sort-Object FullName) {
        $relative = $file.FullName.Substring($editorPrefix.Length).Replace("\", "/")
        $null = $lines.Add(("../editor/{0}|{1}" -f $relative, (Get-FileDigest $file.FullName)))
    }
    $null = $lines.Add(("node|{0}" -f [string]$Toolchain.node.build_version))
    $null = $lines.Add(("pnpm|{0}" -f [string]$Toolchain.pnpm.version))
    $bytes = $script:Utf8NoBom.GetBytes(($lines -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes)) -replace "-", "").ToLowerInvariant() } finally { $sha.Dispose() }
}

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

function Get-FrontendWorkspace { return Join-Path $script:DevelopmentRoot "frontend\workspace" }
function Get-FrontendEditorPluginTarget([string]$Workspace) { return Join-Path $Workspace "node_modules\jiejian-controlled-workspace-resolver" }
function Test-FrontendEditorPluginInstalled([string]$Workspace) {
    $target = Get-FrontendEditorPluginTarget $Workspace
    return (Test-Path -LiteralPath (Join-Path $target "package.json") -PathType Leaf) -and (Test-Path -LiteralPath (Join-Path $target "index.cjs") -PathType Leaf)
}
function Install-FrontendEditorPlugin([string]$Workspace) {
    $source = Get-FrontendEditorPluginRoot
    $target = Get-FrontendEditorPluginTarget $Workspace
    if (-not (Test-Path -LiteralPath (Join-Path $source "package.json") -PathType Leaf) -or -not (Test-Path -LiteralPath (Join-Path $source "index.cjs") -PathType Leaf)) { Fail-Development "frontend-editor" "编辑器解析插件源码不完整" "恢复 scripts/editor/typescript-plugins 后重试" }
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
    if (-not (Test-FrontendEditorPluginInstalled $Workspace)) { Fail-Development "frontend-editor" "编辑器解析插件未进入受控前端工作区" "删除 var/development/frontend/workspace 后重试" }
}
function Sync-FrontendWorkspaceSources([string]$Workspace, $Inputs) {
    $manifestPath = Join-Path $Workspace ".jiejian-source-manifest.json"
    $previous = @()
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        try { $previous = @((Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json).paths) } catch { $previous = @() }
    }
    $current = @($Inputs | ForEach-Object { [string]$_.relative })
    foreach ($relative in $previous | Where-Object { $_ -notin $current }) {
        if ([IO.Path]::IsPathRooted([string]$relative) -or ([string]$relative).Split("/") -contains "..") { continue }
        $stale = Join-Path $Workspace ([string]$relative).Replace("/", "\")
        if (Test-Path -LiteralPath $stale -PathType Leaf) { Remove-Item -LiteralPath $stale -Force }
    }
    foreach ($input in $Inputs) {
        $destination = Join-Path $Workspace ([string]$input.relative).Replace("/", "\")
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath ([string]$input.source) -Destination $destination -Force
    }
    $manifest = [ordered]@{ schema_version = "1"; paths = @($current | Sort-Object) }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Compress), $script:Utf8NoBom)
}

function Prepare-FrontendWorkspace($Toolchain, $Inputs, [string]$DependencyDigest) {
    Resolve-DevelopmentNode $Toolchain $true
    $workspace = Get-FrontendWorkspace
    $workspaceDigest = Join-Path $workspace ".jiejian-dependency-digest"
    $modules = Join-Path $workspace "node_modules\.modules.yaml"
    $healthy = (Test-Path -LiteralPath $workspaceDigest -PathType Leaf) -and ((Get-Content -LiteralPath $workspaceDigest -Raw -Encoding UTF8).Trim() -eq $DependencyDigest) -and (Test-Path -LiteralPath $modules -PathType Leaf) -and (Test-FrontendEditorPluginInstalled $workspace) -and -not (Test-Path -LiteralPath (Join-Path $workspace ".invalid") -PathType Leaf)
    if ($healthy) {
        # 普通源码变化只同步受控工作区输入；依赖视图和 node_modules 不重装。
        Sync-FrontendWorkspaceSources $workspace $Inputs
        return
    }
    Remove-Item -LiteralPath $workspace -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path $workspace -Force | Out-Null
    Sync-FrontendWorkspaceSources $workspace $Inputs
    Push-Location -LiteralPath $workspace
    try {
        Invoke-External "frontend-install" @($script:PnpmRunner + @("install", "--frozen-lockfile", "--store-dir", (Join-Path $script:DevelopmentRoot "cache\pnpm-store")))
        if (-not (Test-Path -LiteralPath $modules -PathType Leaf)) { Fail-Development "frontend-install" "pnpm 未在 var/development/frontend/workspace 生成完整依赖安装视图" "删除该共享 workspace 后重试" }
        # VS Code 禁止工作区覆盖机器级插件探测目录；插件必须随可重建依赖视图安装。
        Install-FrontendEditorPlugin $workspace
        [IO.File]::WriteAllText($workspaceDigest, $DependencyDigest, $script:Utf8NoBom)
    } catch {
        # 失败标记只属于共享开发 workspace；产品 runtime repair 不得越界处理它。
        [IO.File]::WriteAllText((Join-Path $workspace ".invalid"), "frontend-workspace", $script:Utf8NoBom)
        throw
    } finally { Pop-Location }
}

function Invoke-FrontendBuild([string]$Workspace, [string]$Dist) {
    Push-Location -LiteralPath $Workspace
    try {
        $env:JIEJIAN_FRONTEND_OUT_DIR = [IO.Path]::GetFullPath($Dist)
        $env:JIEJIAN_FRONTEND_CACHE_DIR = [IO.Path]::GetFullPath((Join-Path $script:DevelopmentRoot "cache\vite"))
        Invoke-External "frontend-build" @($script:PnpmRunner + @("build"))
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
