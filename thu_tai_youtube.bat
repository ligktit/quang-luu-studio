@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Quang Luu Studio - Thu tai audio tu YouTube

rem ============================================================================
rem  CHAN DOAN KHAU TAI AUDIO
rem
rem  Dung khi do tone bao "Do tone qua lau ... nen da dung". App khong ghi lai
rem  yt-dlp noi gi, nen file nay chay lai dung khau tai do voi day du nhat ky:
rem  ffmpeg nam dau, toc do tai bao nhieu, YouTube tra loi gi.
rem
rem  Chay bang chinh exe -> may khach KHONG can cai Python.
rem ============================================================================

set "SCRIPT_DIR=%~dp0"
set "EXE=%SCRIPT_DIR%QuangLuuStudio.exe"

if not exist "%EXE%" (
    echo [LOI] Khong tim thay QuangLuuStudio.exe canh file nay:
    echo       %EXE%
    echo       Hay chep file .bat nay vao thu muc cai dat cua app roi chay lai.
    pause
    exit /b 1
)

set "LINK=%~1"
if "%LINK%"=="" (
    echo Dan link YouTube cua bai dang bi loi roi bam Enter.
    echo Bo trong va bam Enter thi dung video mau.
    echo.
    set /p "LINK=Link: "
)

echo.
echo Dang thu tai, viec nay co the mat vai phut. Xin cho...
echo.
"%EXE%" --thu-tai %LINK%
set "MA=%ERRORLEVEL%"

echo.
if "%MA%"=="0" (
    echo === KET QUA: TAI DUOC BINH THUONG ===
) else (
    echo === KET QUA: CO VAN DE - gui file bao cao nay cho ky thuat ===
    echo     %APPDATA%\QuangLuuStudio\logs\thu_tai.txt
)
echo.
pause
exit /b %MA%
