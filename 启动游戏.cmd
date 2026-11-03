@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-game.ps1" %*
set "game_launch_exit=%errorlevel%"
if not "%game_launch_exit%"=="0" pause
endlocal & exit /b %game_launch_exit%
