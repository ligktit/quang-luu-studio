@echo off
REM ===========================================================
REM  Quang Luu Studio - Sua loi ket noi may chu do thieu chung chi goc
REM  (app.log: CERTIFICATE_VERIFY_FAILED / unable to get local issuer
REM   certificate; app bao "khong ket noi duoc may chu" khi kich hoat)
REM
REM  Bam dup la chay. Tham so khac (ky thuat):
REM     -Auto -ChiKiem -KhongMoLaiApp -Server "https://..." -AppDir "D:\..."
REM ===========================================================
setlocal
chcp 65001 >nul 2>&1
title Quang Luu Studio - Sua loi chung chi SSL

set "PS1=%~dp0QLS_SuaChungChi.ps1"

if not exist "%PS1%" (
    echo.
    echo [LOI] Khong tim thay file QLS_SuaChungChi.ps1
    echo       Hai file SuaChungChi.bat va QLS_SuaChungChi.ps1 phai nam CUNG mot thu muc.
    echo.
    pause
    exit /b 9
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" echo [KET QUA] May chu xac minh duoc - thu kich hoat lai trong app.
if "%RC%"=="1" echo [KET QUA] Con muc phai lam tay - xem nhat ky tren Desktop.
if "%RC%"=="2" echo [KET QUA] Sua THAT BAI - gui nhat ky tren Desktop cho ky thuat.
echo.
echo App dang mo tu truoc khi sua thi phai TAT HAN roi mo lai.
echo.
pause
exit /b %RC%
