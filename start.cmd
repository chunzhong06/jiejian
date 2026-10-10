@echo off
rem Prefer PowerShell 7; Windows PowerShell 5.1 uses the same startup pipeline.
setlocal
chcp 65001 >nul
where pwsh.exe >nul 2>&1
if not errorlevel 1 (
    set "POWERSHELL_EXE=pwsh.exe"
) else (
    set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
)
set "START_SCRIPT=%~dp0scripts\start.ps1"
if not exist "%START_SCRIPT%" (
    echo Startup script not found: "%START_SCRIPT%" 1>&2
    set "START_EXIT=2"
    goto finish
)
"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%START_SCRIPT%" %*
set "START_EXIT=%ERRORLEVEL%"
:finish
if not "%START_EXIT%"=="0" (
    echo.
    "%POWERSHELL_EXE%" -NoLogo -NoProfile -Command "[Console]::WriteLine(([char[]](0x6309,0x4EFB,0x610F,0x952E,0x5173,0x95ED,0x6B64,0x7A97,0x53E3,0x3002) -join ''))"
    pause >nul
)
endlocal & exit /b %START_EXIT%
