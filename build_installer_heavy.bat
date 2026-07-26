@echo off
chcp 65001 >nul
echo ========================================
echo  Quang Luu Studio - Build Installer (HEAVY)
echo  (co man hinh karaoke nhung - QtWebEngine)
echo ========================================
echo.

REM === Bước 0: Kiểm tra Inno Setup ===
set "ISCC_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if "%ISCC_PATH%"=="" (
    echo [ERROR] Khong tim thay Inno Setup 6!
    echo Vui long tai va cai dat tu: https://jrsoftware.org/isinfo.php
    pause
    exit /b 1
)
echo [OK] Tim thay Inno Setup: %ISCC_PATH%
echo.

REM === Bật biến thể HEAVY cho spec (bundle QtWebEngine) ===
set "QLS_WEBENGINE=1"

REM === Bước 1: Đồng bộ phiên bản ===
echo ----------------------------------------
echo  Buoc 1: Dong bo phien ban
echo ----------------------------------------
python sync_version.py
echo.

REM === Bước 2: Build EXE bằng PyInstaller (distpath rieng: dist_heavy) ===
echo ----------------------------------------
echo  Buoc 2: Build EXE (HEAVY) bang PyInstaller
echo ----------------------------------------
if not exist "QuangLuuStudio.spec" (
    echo [ERROR] Khong tim thay file QuangLuuStudio.spec!
    pause
    exit /b 1
)

echo [INFO] Dang xoa thu muc build/dist_heavy cu...
if exist build rd /s /q build
if exist dist_heavy rd /s /q dist_heavy

echo [INFO] Dang build EXE (QLS_WEBENGINE=1)...
echo.
PyInstaller --distpath dist_heavy QuangLuuStudio.spec

if %errorlevel% neq 0 (
    echo [ERROR] Build EXE that bai!
    pause
    exit /b 1
)

if not exist "dist_heavy\QuangLuuStudio.exe" (
    echo [ERROR] Khong tim thay file dist_heavy\QuangLuuStudio.exe!
    pause
    exit /b 1
)
echo [OK] Build EXE (HEAVY) thanh cong: dist_heavy\QuangLuuStudio.exe
echo.

REM === Bước 3: Build Installer bằng Inno Setup (Variant=heavy) ===
echo ----------------------------------------
echo  Buoc 3: Build Installer (HEAVY)
echo ----------------------------------------
echo [INFO] Dang tao file cai dat...
echo.
"%ISCC_PATH%" /DVariant=heavy QuangLuuStudio_Setup.iss

if %errorlevel% neq 0 (
    echo [ERROR] Tao installer that bai!
    pause
    exit /b 1
)

set "QLS_WEBENGINE="

echo.
echo ========================================
echo  THANH CONG! (HEAVY)
echo ========================================
echo  File cai dat: installer_output\Setup_QuangLuuStudio_Heavy_v...exe
echo ========================================
echo.
pause
