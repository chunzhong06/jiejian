@echo off
REM =============================================================================
REM Windows launcher
REM
REM Position
REM   Minimal stable entry between CMD or double-click launch and PowerShell orchestration.
REM
REM Responsibilities
REM   Enable UTF-8, select PowerShell, and preserve arguments and exit codes.
REM
REM Call chain
REM   user -> start.cmd -> scripts\start.ps1
REM =============================================================================

setlocal
chcp 65001 >nul
REM --- Stage: locate the script and select PowerShell ---
set "START_SCRIPT=%~dp0scripts\start.ps1"
if not exist "%START_SCRIPT%" (
    echo [界鉴] 缺少启动脚本: "%START_SCRIPT%" 1>&2
    endlocal
    exit /b 2
)
where pwsh.exe >nul 2>&1
if not errorlevel 1 (
    set "POWERSHELL_EXE=pwsh.exe"
) else (
    set "POWERSHELL_EXE=powershell.exe"
)
REM --- Stage: run orchestration and preserve its exit code ---
"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%START_SCRIPT%" %*
set "START_EXIT=%ERRORLEVEL%"
endlocal & exit /b %START_EXIT%
