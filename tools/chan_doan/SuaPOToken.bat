@echo off
REM ===========================================================
REM  Quang Luu Studio - Sua loi "PO Token provider: CHUA co (binary)"
REM  roi tai thu 1 bai YouTube de xac nhan.
REM
REM  Bam dup la chay. Co the keo tha link YouTube vao, hoac:
REM     SuaPOToken.bat "https://www.youtube.com/watch?v=..."
REM  Tham so khac (ky thuat): -Auto -BatBuoc -KhongThuTai -ChiThuTai
REM     -ExeFile "C:\...\bgutil-pot-windows-x86_64.exe" -AppDir "D:\..."
REM ===========================================================
setlocal
chcp 65001 >nul 2>&1
title Quang Luu Studio - Sua loi PO Token + thu tai YouTube

set "PS1=%~dp0QLS_SuaPOToken.ps1"

if not exist "%PS1%" (
    echo.
    echo [LOI] Khong tim thay file QLS_SuaPOToken.ps1
    echo       Hai file SuaPOToken.bat va QLS_SuaPOToken.ps1 phai nam CUNG mot thu muc.
    echo.
    pause
    exit /b 9
)

REM Link truyen tran (khong kem -Link) tu gan vao tham so -Link cua ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" echo [KET QUA] PO Token da san sang va tai thu YouTube THANH CONG.
if "%RC%"=="1" echo [KET QUA] Con muc phai lam tay hoac tai thu chua dat - xem nhat ky tren Desktop.
if "%RC%"=="2" echo [KET QUA] Sua THAT BAI - gui nhat ky tren Desktop cho ky thuat.
echo.
echo Nho TAT HAN roi mo lai app sau khi sua.
echo.
pause
exit /b %RC%
