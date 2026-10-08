@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Quang Luu Studio - Khoi phuc am luong trinh duyet

rem Dat lai am luong chrome/edge/... trong Volume Mixer ve 100%.
rem Them chu "watch" sau ten file de canh lien tuc:  khoi_phuc_am_luong_browser.bat watch

set "PS1=%~dp0khoi_phuc_am_luong_browser.ps1"
if /i "%~1"=="watch" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Watch
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
    echo.
    pause
)
