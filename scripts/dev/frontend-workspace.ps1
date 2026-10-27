# 管理前端源码投影、依赖身份和共享安装工作区。

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

function Get-FrontendWorkspace { return Join-Path $script:DevelopmentRoot "frontend\workspace" }

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
