@echo off
rem Source startup requires PowerShell 7; no unverified fallback.
setlocal
chcp 65001 >nul
set "START_SCRIPT=%~dp0scripts\start.ps1"
if not exist "%START_SCRIPT%" (
    echo Startup script not found: "%START_SCRIPT%" 1>&2
    set "START_EXIT=2"
    goto finish
)
where pwsh.exe >nul 2>&1
if not errorlevel 1 (
    set "POWERSHELL_EXE=pwsh.exe"
) else (
    echo PowerShell 7 is required. pwsh.exe was not found. 1>&2
    echo Install PowerShell 7, reopen the terminal, and run start.cmd again. 1>&2
    echo Install: winget install --id Microsoft.PowerShell --source winget 1>&2
    set "START_EXIT=3"
    goto finish
)
"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%START_SCRIPT%" %*
set "START_EXIT=%ERRORLEVEL%"
:finish
if not "%START_EXIT%"=="0" (
    echo.
    echo Startup failed. Press any key to close this window.
    pause >nul
)
endlocal & exit /b %START_EXIT%
