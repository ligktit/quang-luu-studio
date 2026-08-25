@echo off
REM ===========================================================
REM  Quang Luu Studio - VA NHANH cho may dang cai ban 1.7.2
REM
REM  Dung khi khach bao "khong tai duoc nhac YouTube" / "do tone khong chay"
REM  ma CHUA the cai lai app len ban 1.7.3.
REM
REM  Can mang (tai khoang 100 MB) va quyen chay PowerShell.
REM  Go bo:  VaNhanh172.bat -GoBo
REM ===========================================================
chcp 65001 >nul 2>&1
title Quang Luu Studio - Va nhanh 1.7.2

set "PS1=%~dp0QLS_VaNhanh172.ps1"

if not exist "%PS1%" (
    echo.
    echo [LOI] Khong tim thay file QLS_VaNhanh172.ps1
    echo       Hai file VaNhanh172.bat va QLS_VaNhanh172.ps1 phai nam CUNG mot thu muc.
    echo.
    pause
    exit /b 9
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"

echo.
echo Mo lai Quang Luu Studio roi thu do tone mot bai.
echo Neu van hong, chay ChanDoan.bat va gui nhat ky cho ky thuat.
echo.
pause
exit /b %RC%
