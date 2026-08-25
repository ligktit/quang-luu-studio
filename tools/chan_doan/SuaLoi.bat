@echo off
REM ===========================================================
REM  Quang Luu Studio - Sua loi may khach
REM  Chay ChanDoan.bat truoc de biet may bi gi, roi chay file nay.
REM  Moi tep bi sua deu duoc sao luu truoc.
REM ===========================================================
chcp 65001 >nul 2>&1
title Quang Luu Studio - Sua loi

set "PS1=%~dp0QLS_SuaLoi.ps1"

if not exist "%PS1%" (
    echo.
    echo [LOI] Khong tim thay file QLS_SuaLoi.ps1
    echo       Hai file SuaLoi.bat va QLS_SuaLoi.ps1 phai nam CUNG mot thu muc.
    echo.
    pause
    exit /b 9
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="2" echo [KET QUA] Co muc sua that bai - xem nhat ky tren Desktop.
if "%RC%"=="1" echo [KET QUA] Con muc phai lam tay - xem nhat ky tren Desktop.
if "%RC%"=="0" echo [KET QUA] Da xu ly xong.
echo.
echo Mo lai app, thu lai thao tac bi loi, roi chay ChanDoan.bat de kiem tra lai.
echo.
pause
exit /b %RC%
