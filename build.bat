@echo off
echo ========================================
echo Building LiveStudio EXE
echo ========================================
echo.

REM Kiểm tra xem file spec có hiddenimports chưa
findstr /C:"rtmidi" main.spec >nul
if %errorlevel% neq 0 (
    echo [ERROR] File main.spec chua co hiddenimports cho rtmidi!
    echo Vui long kiem tra lai file main.spec
    pause
    exit /b 1
)

echo [INFO] File main.spec da co hiddenimports
echo [INFO] Dang xoa cac thu muc cu...
if exist build rd /s /q build
if exist dist rd /s /q dist

echo [INFO] Dang build EXE tu file spec...
echo.

REM Build từ file spec
PyInstaller main.spec

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo Build thanh cong!
    echo File EXE: dist\main.exe
    echo ========================================
) else (
    echo.
    echo ========================================
    echo Build that bai!
    echo ========================================
)

pause
