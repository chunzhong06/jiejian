@echo off
setlocal
chcp 65001 >nul
set "START_SCRIPT=%~dp0scripts\start.ps1"
if not exist "%START_SCRIPT%" (
    echo Startup script not found: "%START_SCRIPT%" 1>&2
    endlocal
    exit /b 2
)
where pwsh.exe >nul 2>&1
if not errorlevel 1 (
    set "POWERSHELL_EXE=pwsh.exe"
) else (
    set "POWERSHELL_EXE=powershell.exe"
)
"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%START_SCRIPT%" -WaitOnFailure %*
set "START_EXIT=%ERRORLEVEL%"
endlocal & exit /b %START_EXIT%
