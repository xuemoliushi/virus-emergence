@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0local-preview\Test-MobileLayout.ps1" -Case interactive
set "MOBILE_TEST_EXIT=%ERRORLEVEL%"
pause
exit /b %MOBILE_TEST_EXIT%
