@echo off
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-local.ps1" %*
set "SK_EXIT=%ERRORLEVEL%"
if not "%SK_EXIT%"=="0" if "%~1"=="" pause
exit /b %SK_EXIT%
