@echo off
chcp 65001 >nul
echo ========================================
echo  Quang Luu Studio - Build Installer
echo ========================================
echo.

REM === Bước 0: Kiểm tra Inno Setup ===
set "ISCC_PATH="

REM Kiểm tra Inno Setup 6 (các vị trí phổ biến)
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
)
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
)
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
)

if "%ISCC_PATH%"=="" (
    echo [ERROR] Khong tim thay Inno Setup 6!
    echo Vui long tai va cai dat tu: https://jrsoftware.org/isinfo.php
    echo.
    pause
    exit /b 1
)
echo [OK] Tim thay Inno Setup: %ISCC_PATH%
echo.

REM === Bước 1: Build EXE bằng PyInstaller ===
echo ----------------------------------------
echo  Buoc 1: Build EXE bang PyInstaller
echo ----------------------------------------
echo.

if not exist "QuangLuuStudio.spec" (
    echo [ERROR] Khong tim thay file QuangLuuStudio.spec!
    pause
    exit /b 1
)

echo [INFO] Dang xoa thu muc build cu...
if exist build rd /s /q build
if exist dist rd /s /q dist

echo [INFO] Dang build EXE...
echo.
PyInstaller QuangLuuStudio.spec

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build EXE that bai!
    pause
    exit /b 1
)

echo.
echo [OK] Build EXE thanh cong: dist\QuangLuuStudio.exe
echo.

REM Kiểm tra file EXE đã được tạo
if not exist "dist\QuangLuuStudio.exe" (
    echo [ERROR] Khong tim thay file dist\QuangLuuStudio.exe!
    pause
    exit /b 1
)

REM === Bước 2: Build Installer bằng Inno Setup ===
echo ----------------------------------------
echo  Buoc 2: Build Installer bang Inno Setup
echo ----------------------------------------
echo.

if not exist "QuangLuuStudio_Setup.iss" (
    echo [ERROR] Khong tim thay file QuangLuuStudio_Setup.iss!
    pause
    exit /b 1
)

echo [INFO] Dang tao file cai dat...
echo.
"%ISCC_PATH%" QuangLuuStudio_Setup.iss

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Tao installer that bai!
    pause
    exit /b 1
)

echo.
echo ========================================
echo  THANH CONG!
echo ========================================
echo.
echo  File cai dat: installer_output\Setup_QuangLuuStudio_v1.0.0.exe
echo.
echo  Ban co the gui file nay cho nguoi khac
echo  de ho cai dat Quang Luu Studio.
echo ========================================
echo.
pause
