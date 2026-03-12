@echo off
chcp 65001 >nul
echo ========================================
echo  Cai dat QuangLuuMIDI Surface
echo  cho Studio One
echo ========================================
echo.

REM === Tim thu muc Studio One ===
set "SURFACE_DIR="

REM Studio One 7
if exist "%APPDATA%\PreSonus\Studio One 7" (
    set "SURFACE_DIR=%APPDATA%\PreSonus\Studio One 7\User Devices\QuangLuuMIDI"
    echo [OK] Tim thay Studio One 7
)

REM Studio One 6
if "%SURFACE_DIR%"=="" (
    if exist "%APPDATA%\PreSonus\Studio One 6" (
        set "SURFACE_DIR=%APPDATA%\PreSonus\Studio One 6\User Devices\QuangLuuMIDI"
        echo [OK] Tim thay Studio One 6
    )
)

REM Studio One 5
if "%SURFACE_DIR%"=="" (
    if exist "%APPDATA%\PreSonus\Studio One 5" (
        set "SURFACE_DIR=%APPDATA%\PreSonus\Studio One 5\User Devices\QuangLuuMIDI"
        echo [OK] Tim thay Studio One 5
    )
)

if "%SURFACE_DIR%"=="" (
    echo [ERROR] Khong tim thay Studio One!
    echo Vui long cai dat Studio One truoc.
    echo.
    pause
    exit /b 1
)

echo [INFO] Thu muc dich: %SURFACE_DIR%
echo.

REM === Tao thu muc neu chua co ===
if not exist "%SURFACE_DIR%" (
    mkdir "%SURFACE_DIR%"
    echo [OK] Da tao thu muc QuangLuuMIDI
)

REM === Copy file surface ===
set "SRC_DIR=%~dp0studio_one"

if not exist "%SRC_DIR%\QuangLuuMIDI.surface.xml" (
    echo [ERROR] Khong tim thay file surface tai: %SRC_DIR%
    pause
    exit /b 1
)

copy /Y "%SRC_DIR%\QuangLuuMIDI.surface.xml" "%SURFACE_DIR%\" >nul
copy /Y "%SRC_DIR%\deviceinfo.xml" "%SURFACE_DIR%\" >nul

echo [OK] Da copy QuangLuuMIDI.surface.xml
echo [OK] Da copy deviceinfo.xml
echo.
echo ========================================
echo  CAI DAT THANH CONG!
echo ========================================
echo.
echo  Buoc tiep theo trong Studio One:
echo  1. Mo Studio One
echo  2. Vao Options ^> External Devices ^> Add
echo  3. Chon "QuangLuuMIDI" tu danh sach
echo  4. Chon MIDI port: QuangLuuMIDI (loopMIDI)
echo.
pause
