@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Quang Luu Studio - Chua loi "phan tich am dieu bi loi"

rem ============================================================================
rem  CHUA LOI DO TONE (cache numba hong)
rem
rem  Dung khi app bao "Da tai duoc audio nhung phan tich am dieu bi loi" LAP DI
rem  LAP LAI, du da doi bai / doi mang. Nguyen nhan: file cache bien dich cua
rem  numba bi ghi do (mat dien, tat ngang, diet virus chen vao) nen con toan
rem  byte 0x00; numba khong tu chua, phai xoa di cho no bien dich lai.
rem
rem  File nay CHAY DOC LAP: khong can cai Python, khong can ban app moi, chep
rem  di dau cung chay duoc. Xoa cache la viec an toan - app tu tao lai, chi ton
rem  them muoi giay o lan do tone dau tien.
rem ============================================================================

set "LOGDIR=%APPDATA%\QuangLuuStudio\logs"
set "LOGFILE=%LOGDIR%\chua_do_tone.txt"
set "TONG=0"

echo.
echo ================================================================
echo   QUANG LUU STUDIO - CHUA LOI DO TONE
echo   (xoa cache bien dich numba bi hong)
echo ================================================================
echo.

rem --- App dang chay thi bao dong truoc ---------------------------------------
tasklist /fi "imagename eq QuangLuuStudio.exe" 2>nul | find /i "QuangLuuStudio.exe" >nul
if not errorlevel 1 (
    echo [CHU Y] Quang Luu Studio dang mo.
    echo         Hay TAT app truoc cho chac, roi bam phim bat ky de tiep tuc.
    echo.
    pause
    echo.
)

rem --- Cac thu muc cache can don ---------------------------------------------
call :DonThuMuc "%LOCALAPPDATA%\numba\Cache"            "Cache chung cua numba (ban cu)"
call :DonThuMuc "%APPDATA%\QuangLuuStudio\numba_cache"  "Cache rieng cua app (ban 1.7.8 tro len)"

echo ----------------------------------------------------------------
if "%TONG%"=="0" (
    echo KET QUA: khong tim thay file cache nao de xoa.
    echo.
    echo   Neu app VAN bao loi phan tich am dieu thi nguyen nhan nam cho khac.
    echo   Hay gui file nay cho ky thuat:
    echo       %APPDATA%\QuangLuuStudio\logs\errors.log
) else (
    echo KET QUA: da xoa %TONG% file cache.
    echo.
    echo   Gio mo lai Quang Luu Studio va thu Do Tone.
    echo   Lan do tone DAU TIEN se cham hon khoang muoi giay - do la binh thuong,
    echo   app dang bien dich lai. Nhung lan sau se nhanh nhu cu.
)
echo ----------------------------------------------------------------
echo.

rem --- Ghi nhat ky de khach gui lai neu can ----------------------------------
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
if exist "%LOGDIR%" (
    >>"%LOGFILE%" echo [%DATE% %TIME%] Da xoa %TONG% file cache numba.
    echo Da ghi nhat ky: %LOGFILE%
    echo.
)

pause
exit /b 0


rem ============================================================================
:DonThuMuc
rem  %~1 = duong dan thu muc, %~2 = mo ta
set "MUC=%~1"
echo [*] %~2
echo     %MUC%

if not exist "%MUC%" (
    echo     -^> khong co thu muc nay, bo qua.
    echo.
    goto :eof
)

set "SOFILE=0"
for /f %%N in ('dir /b /s /a-d "%MUC%" 2^>nul ^| find /c /v ""') do set "SOFILE=%%N"

if "%SOFILE%"=="0" (
    echo     -^> thu muc rong, bo qua.
    echo.
    goto :eof
)

rmdir /s /q "%MUC%" 2>nul
if exist "%MUC%" (
    echo     -^> KHONG XOA DUOC ^(app con dang mo, hoac thieu quyen^).
    echo        Hay tat app roi chay lai file nay.
) else (
    set /a TONG=TONG + %SOFILE%
    echo     -^> da xoa %SOFILE% file.
)
echo.
goto :eof
