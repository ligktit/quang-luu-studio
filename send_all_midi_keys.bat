@echo off
chcp 65001 >nul
setlocal

echo ============================================================
echo   Quang Luu Studio - Send ALL MIDI Keys
echo   (Khong can Python - dung winmm.dll)
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
set "PS_SCRIPT=%SCRIPT_DIR%send_all_midi_keys.ps1"

if not exist "%PS_SCRIPT%" (
    echo [LOI] Khong tim thay file: send_all_midi_keys.ps1
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

endlocal
