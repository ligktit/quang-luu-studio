@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
REM Roi thu muc cai: cmd va moi tien trinh no mo (loopMIDI...) giu CWD o day thi
REM Update.exe khong doi ten duoc thu muc cai, ban cap nhat khong ap dung duoc.
REM Moi duong dan trong file nay deu la duong dan tuyet doi.
cd /d "%USERPROFILE%"

set "SCRIPT_DIR=%~dp0"
set "QLS_DATA=%APPDATA%\QuangLuuStudio"
set "APP_CONFIG=%QLS_DATA%\app_config_overrides.json"
set "INTERACTIVE=1"

REM Phan nguoi dung doi cua app_config nam o %APPDATA% (thu muc cai co the
REM read-only va bi thay moi lan cap nhat). Chua co thi tao file rong.
if not exist "%QLS_DATA%" mkdir "%QLS_DATA%"
if not exist "%APP_CONFIG%" (
    powershell -NoProfile -Command "[IO.File]::WriteAllText('%APP_CONFIG%', '{}', (New-Object Text.UTF8Encoding($false)))"
)

set "MODE="
set "BROWSER="
set "PROFILE="
set "COOKIE_FILE="

if /I "%~1"=="--auto" (
    set "INTERACTIVE=0"
    set "MODE=browser"
    set "BROWSER=auto"
    goto :apply
)
if /I "%~1"=="--edge" (
    set "INTERACTIVE=0"
    set "MODE=browser"
    set "BROWSER=edge"
    set "PROFILE=%~2"
    goto :apply
)
if /I "%~1"=="--chrome" (
    set "INTERACTIVE=0"
    set "MODE=browser"
    set "BROWSER=chrome"
    set "PROFILE=%~2"
    goto :apply
)
if /I "%~1"=="--brave" (
    set "INTERACTIVE=0"
    set "MODE=browser"
    set "BROWSER=brave"
    set "PROFILE=%~2"
    goto :apply
)
if /I "%~1"=="--firefox" (
    set "INTERACTIVE=0"
    set "MODE=browser"
    set "BROWSER=firefox"
    set "PROFILE=%~2"
    goto :apply
)
if /I "%~1"=="--opera" (
    set "INTERACTIVE=0"
    set "MODE=browser"
    set "BROWSER=opera"
    set "PROFILE=%~2"
    goto :apply
)
if /I "%~1"=="--vivaldi" (
    set "INTERACTIVE=0"
    set "MODE=browser"
    set "BROWSER=vivaldi"
    set "PROFILE=%~2"
    goto :apply
)
if /I "%~1"=="--none" (
    set "INTERACTIVE=0"
    set "MODE=browser"
    set "BROWSER=none"
    goto :apply
)
if /I "%~1"=="--cookie-file" (
    set "INTERACTIVE=0"
    set "MODE=file"
    set "COOKIE_FILE=%~2"
    goto :apply
)

echo ========================================
echo   Cau hinh YouTube cookie cho app
echo ========================================
echo.
echo File config:
echo   %APP_CONFIG%
echo.
echo Chon cach app lay cookie:
echo   1. Auto ^(tu doan browser, khuyen dung^)
echo   2. Edge ^(khuyen dung tren Windows^)
echo   3. Chrome ^(de loi neu Chrome dang mo^)
echo   4. Brave
echo   5. Firefox
echo   6. Opera
echo   7. Vivaldi
echo   8. Cookie file ^(.txt Netscape^)
echo   9. Tat doc cookie tu browser
echo.
set /p "CHOICE=Nhap lua chon (1-9): "

if "%CHOICE%"=="1" (
    set "MODE=browser"
    set "BROWSER=auto"
    goto :apply
)
if "%CHOICE%"=="2" (
    set "MODE=browser"
    set "BROWSER=edge"
    goto :ask_profile
)
if "%CHOICE%"=="3" (
    set "MODE=browser"
    set "BROWSER=chrome"
    goto :ask_profile
)
if "%CHOICE%"=="4" (
    set "MODE=browser"
    set "BROWSER=brave"
    goto :ask_profile
)
if "%CHOICE%"=="5" (
    set "MODE=browser"
    set "BROWSER=firefox"
    goto :ask_profile
)
if "%CHOICE%"=="6" (
    set "MODE=browser"
    set "BROWSER=opera"
    goto :ask_profile
)
if "%CHOICE%"=="7" (
    set "MODE=browser"
    set "BROWSER=vivaldi"
    goto :ask_profile
)
if "%CHOICE%"=="8" (
    set "MODE=file"
    goto :ask_cookie_file
)
if "%CHOICE%"=="9" (
    set "MODE=browser"
    set "BROWSER=none"
    goto :apply
)

echo [ERROR] Lua chon khong hop le.
pause
exit /b 1

:ask_profile
echo.
echo Vi du profile:
echo   Edge/Chrome/Brave: Default, Profile 1, Profile 2
echo   Firefox: de trong neu khong chac
echo.
set /p "PROFILE=Nhap ten profile (bo trong neu muon mac dinh): "
goto :apply

:ask_cookie_file
echo.
set /p "COOKIE_FILE=Nhap duong dan file cookie .txt: "
if not defined COOKIE_FILE (
    echo [ERROR] Ban chua nhap duong dan file cookie.
    pause
    exit /b 1
)
if not exist "%COOKIE_FILE%" (
    echo [ERROR] Khong tim thay file cookie:
    echo         %COOKIE_FILE%
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)
goto :apply

:apply
echo.
echo [INFO] Dang cap nhat app_config_overrides.json...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$path = [System.IO.Path]::GetFullPath('%APP_CONFIG%');" ^
    "$config = [IO.File]::ReadAllText($path).TrimStart([char]0xFEFF) | ConvertFrom-Json;" ^
    "if (-not $config.PSObject.Properties['youtube_cookie_browser']) { $config | Add-Member -NotePropertyName youtube_cookie_browser -NotePropertyValue '' };" ^
    "if (-not $config.PSObject.Properties['youtube_cookie_profile']) { $config | Add-Member -NotePropertyName youtube_cookie_profile -NotePropertyValue '' };" ^
    "if (-not $config.PSObject.Properties['youtube_cookie_file']) { $config | Add-Member -NotePropertyName youtube_cookie_file -NotePropertyValue '' };" ^
    "$mode = '%MODE%';" ^
    "$browser = '%BROWSER%';" ^
    "$profile = '%PROFILE%';" ^
    "$cookieFile = '%COOKIE_FILE%';" ^
    "if ($mode -eq 'file') { $config.youtube_cookie_browser = 'none'; $config.youtube_cookie_profile = ''; $config.youtube_cookie_file = $cookieFile } else { $config.youtube_cookie_browser = $browser; $config.youtube_cookie_profile = $profile; $config.youtube_cookie_file = '' };" ^
    "$json = $config | ConvertTo-Json -Depth 20;" ^
    "[System.IO.File]::WriteAllText($path, $json + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)));" ^
    "Write-Host '[OK] Da cap nhat xong:';" ^
    "Write-Host ('  youtube_cookie_browser = ' + $config.youtube_cookie_browser);" ^
    "Write-Host ('  youtube_cookie_profile = ' + $config.youtube_cookie_profile);" ^
    "Write-Host ('  youtube_cookie_file    = ' + $config.youtube_cookie_file)"

if errorlevel 1 (
    echo [ERROR] Cap nhat app_config_overrides.json that bai.
    pause
    exit /b 1
)

echo.
echo [OK] Cau hinh da duoc luu.
echo [INFO] Neu app dang mo, hay tat va mo lai app.
echo.
echo Cach chay nhanh:
echo   %~nx0 --auto
echo   %~nx0 --edge "Default"
echo   %~nx0 --chrome "Profile 1"
echo   %~nx0 --cookie-file "D:\path\youtube_cookies.txt"
echo.
echo Meo:
echo   Neu Chrome bao "Could not copy ... cookie database", hay thu Edge hoac dong hoan toan Chrome.
echo.
if "%INTERACTIVE%"=="1" pause
exit /b 0
