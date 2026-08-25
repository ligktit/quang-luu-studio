@echo off
REM ===========================================================
REM  Quang Luu Studio - Chan doan may khach
REM  Bam dup file nay de kiem tra. Script chi DOC, khong sua gi.
REM ===========================================================
chcp 65001 >nul 2>&1
title Quang Luu Studio - Chan doan may

set "PS1=%~dp0QLS_ChanDoan.ps1"

if not exist "%PS1%" (
    echo.
    echo [LOI] Khong tim thay file QLS_ChanDoan.ps1
    echo       Hai file ChanDoan.bat va QLS_ChanDoan.ps1 phai nam CUNG mot thu muc.
    echo.
    pause
    exit /b 9
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="2" echo [KET QUA] Co loi NANG - xem phan "CAN XU LY NGAY" trong bao cao.
if "%RC%"=="1" echo [KET QUA] Co canh bao - xem phan "NEN KIEM TRA THEM" trong bao cao.
if "%RC%"=="0" echo [KET QUA] Khong phat hien van de nao.
echo.
echo Bao cao da duoc luu ra Desktop. Gui file .txt do cho ky thuat.
echo.
pause
exit /b %RC%
