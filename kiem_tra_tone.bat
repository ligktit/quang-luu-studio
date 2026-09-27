@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Quang Luu Studio - Tu kiem tra co che do tone

rem Kiem tra co che chua cache numba (thu pham lam "phan tich am dieu bi loi"
rem lap di lap lai). Chay bang chinh file exe nen may khach KHONG can cai Python.

set "SCRIPT_DIR=%~dp0"
set "EXE=%SCRIPT_DIR%QuangLuuStudio.exe"

if not exist "%EXE%" (
    echo [LOI] Khong tim thay QuangLuuStudio.exe canh file nay:
    echo       %EXE%
    echo       Hay chep file .bat nay vao thu muc cai dat cua app roi chay lai.
    pause
    exit /b 1
)

echo Dang kiem tra, cho vai giay...
echo.
"%EXE%" --tu-kiem-tra %*
set "MA=%ERRORLEVEL%"

echo.
if "%MA%"=="0" (
    echo === KET QUA: TAT CA DEU DAT ===
) else (
    echo === KET QUA: CO LOI - gui file bao cao cho ky thuat ===
    echo     %APPDATA%\QuangLuuStudio\logs\tu_kiem_tra.txt
)
echo.
echo Muon kiem tan goc (nap librosa that, cham hon) thi chay:
echo     kiem_tra_tone.bat --day-du
echo.
pause
exit /b %MA%
