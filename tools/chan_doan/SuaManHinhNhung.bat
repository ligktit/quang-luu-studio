@echo off
REM ===========================================================
REM  Quang Luu Studio - Sua loi "nap QtWebEngine that bai"
REM  (o "Man hinh karaoke nhung" trong Thiet lap bi mo)
REM
REM  Bam dup la chay. Tham so (ky thuat):
REM     -Xem          chi kiem tra, khong sua
REM     -Auto         khong hoi C/K
REM     -LoaiTruTemp  loai tru ca %TEMP% khoi Defender
REM     -KhongMoApp   khong mo app de xac nhan
REM     -AppDir "D:\QuangLuuStudio"
REM ===========================================================
setlocal
chcp 65001 >nul 2>&1
title Quang Luu Studio - Sua loi man hinh karaoke nhung

set "PS1=%~dp0QLS_SuaManHinhNhung.ps1"

if not exist "%PS1%" (
    echo.
    echo [LOI] Khong tim thay file QLS_SuaManHinhNhung.ps1
    echo       Hai file SuaManHinhNhung.bat va QLS_SuaManHinhNhung.ps1 phai nam CUNG mot thu muc.
    echo.
    pause
    exit /b 9
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" echo [KET QUA] Man hinh karaoke nhung DUNG DUOC. Bat lai trong Thiet lap.
if "%RC%"=="1" echo [KET QUA] Con muc phai lam tay hoac chua xac nhan - xem nhat ky tren Desktop.
if "%RC%"=="2" echo [KET QUA] Sua THAT BAI - gui nhat ky tren Desktop cho ky thuat.
echo.
pause
exit /b %RC%
