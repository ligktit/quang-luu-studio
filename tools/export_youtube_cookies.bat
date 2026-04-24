@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

:: ============================================================
:: Xuat YouTube cookies tu trinh duyet ra file .txt
:: De app co the dung khi trinh duyet dang mo (tranh loi
:: "Could not copy Chrome cookie database")
::
:: Cach dung:
::   Chay script nay mot lan → file cookie duoc luu tu dong.
::   App se tu doc file do trong cac lan chay tiep theo.
::
:: Cach chay nhanh (khong hoi):
::   export_youtube_cookies.bat --chrome
::   export_youtube_cookies.bat --edge
::   export_youtube_cookies.bat --firefox   ← khong can dong Firefox
::   export_youtube_cookies.bat --brave
:: ============================================================

set "APPDATA_DIR=%APPDATA%\QuangLuuStudio"
set "COOKIE_OUT=%APPDATA_DIR%\youtube_cookies.txt"
set "APP_CONFIG=%~dp0..\app_config.json"
set "BROWSER="
set "PROFILE="
set "INTERACTIVE=1"

:: ── Xu ly tham so dong lenh ──────────────────────────────────
if /I "%~1"=="--chrome"  ( set "BROWSER=chrome"  & set "PROFILE=%~2" & set "INTERACTIVE=0" & goto :run )
if /I "%~1"=="--edge"    ( set "BROWSER=edge"    & set "PROFILE=%~2" & set "INTERACTIVE=0" & goto :run )
if /I "%~1"=="--firefox" ( set "BROWSER=firefox" & set "PROFILE=%~2" & set "INTERACTIVE=0" & goto :run )
if /I "%~1"=="--brave"   ( set "BROWSER=brave"   & set "PROFILE=%~2" & set "INTERACTIVE=0" & goto :run )
if /I "%~1"=="--opera"   ( set "BROWSER=opera"   & set "PROFILE=%~2" & set "INTERACTIVE=0" & goto :run )
if /I "%~1"=="--vivaldi" ( set "BROWSER=vivaldi" & set "PROFILE=%~2" & set "INTERACTIVE=0" & goto :run )

:: ── Menu tuong tac ───────────────────────────────────────────
echo.
echo  =====================================================
echo    Xuat YouTube Cookies - Quang Luu Studio
echo  =====================================================
echo.
echo  Muc dich: Luu cookie ra file de app dung khi trinh
echo  duyet dang mo (tranh loi "Could not copy cookie DB").
echo.
echo  File se duoc luu tai:
echo    %COOKIE_OUT%
echo.
echo  LUU ?: Firefox co the xuat cookie khi dang mo.
echo  Chrome/Edge/Brave can DONG HOAN TOAN truoc khi xuat.
echo.
echo  Chon trinh duyet:
echo    1. Firefox   (KHUYEN DUNG - co the xuat khi dang mo)
echo    2. Edge
echo    3. Chrome
echo    4. Brave
echo    5. Opera
echo    6. Vivaldi
echo.
set /p "CHOICE=Lua chon (1-6) [1]: "
if not defined CHOICE set "CHOICE=1"

if "%CHOICE%"=="1" ( set "BROWSER=firefox"  & goto :ask_profile )
if "%CHOICE%"=="2" ( set "BROWSER=edge"     & goto :ask_close )
if "%CHOICE%"=="3" ( set "BROWSER=chrome"   & goto :ask_close )
if "%CHOICE%"=="4" ( set "BROWSER=brave"    & goto :ask_close )
if "%CHOICE%"=="5" ( set "BROWSER=opera"    & goto :ask_close )
if "%CHOICE%"=="6" ( set "BROWSER=vivaldi"  & goto :ask_close )

echo [LOI] Lua chon khong hop le.
pause & exit /b 1

:ask_close
echo.
echo  [!] Ban can DONG HOAN TOAN %BROWSER% truoc khi tiep tuc.
echo      (Chromium lock file cookie khi dang mo)
echo.
set /p "CONFIRM=Da dong %BROWSER% chua? (y/N): "
if /I not "%CONFIRM%"=="y" (
    echo [HUY] Ban chua dong %BROWSER%. Hay dong browser roi chay lai.
    pause & exit /b 0
)
goto :ask_profile

:ask_profile
echo.
set /p "PROFILE=Profile (bo trong neu mac dinh, vd: 'Default', 'Profile 1'): "
goto :run

:run
:: ── Kiem tra Python + yt-dlp ─────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python. Hay cai Python va thu lai.
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)

python -c "import yt_dlp" >nul 2>&1
if errorlevel 1 (
    echo [LOI] yt-dlp chua duoc cai. Chay: pip install yt-dlp
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)

:: Tao thu muc neu chua co
if not exist "%APPDATA_DIR%" mkdir "%APPDATA_DIR%"

echo.
echo [1/3] Xuat cookie tu %BROWSER%...
echo       Output: %COOKIE_OUT%
echo.

:: Build cookiesfrombrowser argument
set "COOKIE_SRC=%BROWSER%"
if defined PROFILE if not "%PROFILE%"=="" set "COOKIE_SRC=%BROWSER%+::%PROFILE%"

python -c ^
    "import yt_dlp, sys; ^
     profile = '%PROFILE%'.strip(); ^
     src = ('%BROWSER%', profile) if profile else ('%BROWSER%',); ^
     opts = {'cookiesfrombrowser': src, 'cookiefile': r'%COOKIE_OUT%', 'skip_download': True, 'quiet': False, 'no_warnings': False}; ^
     ydl = yt_dlp.YoutubeDL(opts); ^
     ydl.__enter__(); ^
     ydl.extract_info('https://www.youtube.com/', download=False); ^
     ydl.__exit__(None,None,None); ^
     print('[OK] Xuat cookie thanh cong')"

if errorlevel 1 (
    echo.
    echo [LOI] Khong the xuat cookie tu %BROWSER%.
    echo.
    echo  Nguyen nhan co the:
    echo   - Browser van dang mo (voi Chrome/Edge/Brave)
    echo   - Chua dang nhap YouTube tren browser nay
    echo   - Profile khong dung
    echo.
    echo  Goi y: Thu dung Firefox (lua chon 1).
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)

:: Kiem tra file da duoc tao
if not exist "%COOKIE_OUT%" (
    echo [LOI] File cookie khong duoc tao. Thu lai.
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)

for %%A in ("%COOKIE_OUT%") do set "FSIZE=%%~zA"
if "%FSIZE%"=="0" (
    echo [LOI] File cookie trong (0 bytes). Browser co the chua dang nhap YouTube.
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)

echo.
echo [2/3] File cookie da duoc luu (%FSIZE% bytes).
echo.

:: Update app_config.json neu ton tai
if exist "%APP_CONFIG%" (
    echo [3/3] Cap nhat app_config.json...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
        "$p = [IO.Path]::GetFullPath('%APP_CONFIG%');" ^
        "$c = Get-Content -Raw $p | ConvertFrom-Json;" ^
        "if (-not $c.PSObject.Properties['youtube_cookie_file']) { $c | Add-Member youtube_cookie_file '' };" ^
        "if (-not $c.PSObject.Properties['youtube_cookie_browser']) { $c | Add-Member youtube_cookie_browser 'none' };" ^
        "$c.youtube_cookie_file = r'%COOKIE_OUT%';" ^
        "$c.youtube_cookie_browser = 'none';" ^
        "[IO.File]::WriteAllText($p, ($c | ConvertTo-Json -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)));" ^
        "Write-Host '[OK] app_config.json da duoc cap nhat'"
) else (
    echo [3/3] (Khong tim thay app_config.json - bo qua cap nhat config)
)

echo.
echo  =====================================================
echo   HOAN THANH! Cookie da duoc xuat thanh cong.
echo.
echo   File: %COOKIE_OUT%
echo.
echo   App se tu dong dung file nay tu lan chay tiep theo.
echo   Neu cookie het han (~1 thang), chay lai script nay.
echo  =====================================================
echo.
if "%INTERACTIVE%"=="1" pause
exit /b 0
