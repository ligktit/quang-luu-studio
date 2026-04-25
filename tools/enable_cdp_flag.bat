@echo off
chcp 65001 >nul 2>&1
title Quang Luu Studio - Enable CDP Flag for Browsers
color 0B

echo.
echo  ╔══════════════════════════════════════════════════════════╗
echo  ║   Quang Luu Studio - Browser CDP Flag Installer         ║
echo  ║   Them --remote-debugging-port=9222 vao shortcut        ║
echo  ║   Edge / Chrome / Brave de CDP tu ket noi               ║
echo  ╚══════════════════════════════════════════════════════════╝
echo.

:: Get directory of this batch file
set "SCRIPT_DIR=%~dp0"

:: Run the PowerShell script
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%_apply_cdp.ps1"

echo.
echo  ──────────────────────────────────────────────────────────
echo   Neu co shortcut bi loi (ProgramData), hay chay lai
echo   bang cach: Click phai ^> Run as Administrator
echo  ──────────────────────────────────────────────────────────
echo.
echo  Nhan phim bat ky de dong...
pause >nul
