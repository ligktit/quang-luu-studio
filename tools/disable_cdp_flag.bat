@echo off
chcp 65001 >nul 2>&1
title Quang Luu Studio - Remove CDP Flag from Browsers
color 0E

echo.
echo  ============================================================
echo    Quang Luu Studio - Browser CDP Flag Remover
echo    Go bo --remote-debugging-port khoi shortcut
echo    Edge / Chrome / Brave
echo  ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%_remove_cdp.ps1"

echo.
echo  Nhan phim bat ky de dong...
pause >nul
