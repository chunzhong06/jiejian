# 把编辑器依赖解析插件安装到受控前端工作区。

function Get-FrontendEditorPluginRoot { return Join-Path $script:ProjectRoot "scripts\editor\typescript-plugins\jiejian-controlled-workspace-resolver" }

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
