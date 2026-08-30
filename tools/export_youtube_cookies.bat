@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

:: ============================================================
:: Xuat YouTube cookies tu trinh duyet ra file .txt
::
:: CANH BAO QUAN TRONG - doc truoc khi sua script nay:
::   Tu Chrome 127 (va Edge/Brave/Opera/Vivaldi cung nhan), cookie
::   duoc ma hoa bang khoa cot vao chinh trinh duyet (App-Bound
::   Encryption). yt-dlp doc thang file thi LUON tit, va
::   *** DONG TRINH DUYET KHONG CUU DUOC ***
::   vi day khong phai chuyen file bi khoa ma la khong co khoa
::   giai ma. Dung viet lai loi khuyen "dong browser roi thu lai".
::   Chi tiet + so lieu do: docs\COOKIE_TRINH_DUYET_VA_CDP.md
::
::   Duong dung cho Chromium: MO trinh duyet len (co co
::   --remote-debugging-port) roi lay cookie qua CDP - lua chon 1.
::   Firefox khong dinh App-Bound Encryption nen van doc thang duoc.
::
:: Cach dung:
::   Chay script nay mot lan → file cookie duoc luu tu dong.
::   App se tu doc file do trong cac lan chay tiep theo.
::
:: Cach chay nhanh (khong hoi):
::   export_youtube_cookies.bat --cdp       ← trinh duyet DANG MO
::   export_youtube_cookies.bat --firefox   ← khong can dong Firefox
::   export_youtube_cookies.bat --chrome    ← gan nhu chac chan tit
::   export_youtube_cookies.bat --edge
::   export_youtube_cookies.bat --brave
:: ============================================================

set "APPDATA_DIR=%APPDATA%\QuangLuuStudio"
set "COOKIE_OUT=%APPDATA_DIR%\youtube_cookies.txt"
set "APP_CONFIG=%~dp0..\app_config.json"
set "BROWSER="
set "PROFILE="
set "INTERACTIVE=1"

:: ── Xu ly tham so dong lenh ──────────────────────────────────
if /I "%~1"=="--cdp"     ( set "INTERACTIVE=0" & goto :run_cdp )
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
echo  Muc dich: Luu cookie YouTube ra file de app dung.
echo.
echo  File se duoc luu tai:
echo    %COOKIE_OUT%
echo.
echo  LUU Y: Chrome/Edge/Brave tu ban 127 ma hoa cookie bang khoa
echo  cot vao chinh trinh duyet. DONG TRINH DUYET KHONG GIUP GI -
echo  nguoc lai, phai MO no len thi moi lay duoc (lua chon 1).
echo.
echo  Chon cach lay:
echo    1. Trinh duyet DANG MO, qua CDP  (KHUYEN DUNG cho Chrome/Edge/Brave)
echo    2. Firefox   (doc thang duoc, ke ca khi dang mo)
echo    3. Edge      (chi chay duoc voi ban cu hon 127)
echo    4. Chrome    (chi chay duoc voi ban cu hon 127)
echo    5. Brave     (chi chay duoc voi ban cu hon 127)
echo    6. Opera
echo    7. Vivaldi
echo.
set /p "CHOICE=Lua chon (1-7) [1]: "
if not defined CHOICE set "CHOICE=1"

if "%CHOICE%"=="1" goto :run_cdp
if "%CHOICE%"=="2" ( set "BROWSER=firefox"  & goto :ask_profile )
if "%CHOICE%"=="3" ( set "BROWSER=edge"     & goto :ask_profile )
if "%CHOICE%"=="4" ( set "BROWSER=chrome"   & goto :ask_profile )
if "%CHOICE%"=="5" ( set "BROWSER=brave"    & goto :ask_profile )
if "%CHOICE%"=="6" ( set "BROWSER=opera"    & goto :ask_profile )
if "%CHOICE%"=="7" ( set "BROWSER=vivaldi"  & goto :ask_profile )

echo [LOI] Lua chon khong hop le.
pause & exit /b 1

:: ── Lay cookie tu trinh duyet DANG CHAY qua CDP ──────────────
:: Duong duy nhat con dung duoc voi Chromium >= 127: khong tu giai
:: ma nua ma nho chinh trinh duyet giai ma ho. Yeu cau trinh duyet
:: dang mo VOI co --remote-debugging-port (shortcut cua Quang Luu
:: Studio da co san, hoac chay tools\_apply_cdp.ps1 mot lan).
:run_cdp
python --version >nul 2>&1
if errorlevel 1 (
    echo [LOI] Khong tim thay Python. Hay cai Python va thu lai.
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)
echo.
echo [1/3] Xin cookie tu trinh duyet dang chay qua CDP...
echo       Output: %COOKIE_OUT%
echo.
:: Mot dong duy nhat - KHONG tach dong bang dau ^ o day: trong chuoi nam giua
:: hai dau nhay kep, cmd KHONG coi ^ la ky tu noi dong ma day thang no vao ma
:: Python, thanh "SyntaxError: invalid syntax".
pushd "%~dp0.."
python -c "import sys; from core import cdp_cookies; sys.exit(0 if cdp_cookies.harvest_to_file(output_path=r'%COOKIE_OUT%') else 1)"
set "CDP_RC=%ERRORLEVEL%"
popd
if not "%CDP_RC%"=="0" (
    echo.
    echo [LOI] Khong xin duoc cookie qua CDP.
    echo.
    echo  Nguyen nhan co the:
    echo   - Trinh duyet chua mo. Hay MO no len roi chay lai.
    echo   - Trinh duyet mo khong co co --remote-debugging-port.
    echo     Mo bang shortcut cua Quang Luu Studio, hoac chay
    echo     tools\_apply_cdp.ps1 mot lan roi mo lai trinh duyet.
    echo   - Chua dang nhap YouTube tren trinh duyet do.
    echo.
    echo  Con mot duong nua: cai Firefox, dang nhap YouTube tren do,
    echo  roi chay lai script nay va chon 2.
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)
goto :done

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
    echo   - %BROWSER% tu ban 127 ma hoa cookie bang khoa cot vao chinh
    echo     no ^(App-Bound Encryption^). Duong nay coi nhu tit han, va
    echo     DONG TRINH DUYET CUNG KHONG GIUP GI.
    echo   - Chua dang nhap YouTube tren browser nay
    echo   - Profile khong dung
    echo.
    echo  Goi y: chay lai va chon 1 ^(lay qua CDP, trinh duyet DANG MO^),
    echo  hoac chon 2 neu may co Firefox.
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)

:done
:: Kiem tra file da duoc tao
if not exist "%COOKIE_OUT%" (
    echo [LOI] File cookie khong duoc tao. Thu lai.
    if "%INTERACTIVE%"=="1" pause
    exit /b 1
)

for %%A in ("%COOKIE_OUT%") do set "FSIZE=%%~zA"
if "%FSIZE%"=="0" (
    echo [LOI] File cookie trong ^(0 bytes^). Browser co the chua dang nhap YouTube.
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
        "$c.youtube_cookie_file = '%COOKIE_OUT%';" ^
        "$c.youtube_cookie_browser = 'none';" ^
        "[IO.File]::WriteAllText($p, ($c | ConvertTo-Json -Depth 20) + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)));" ^
        "Write-Host '[OK] app_config.json da duoc cap nhat'"
) else (
    echo [3/3] Khong tim thay app_config.json - bo qua cap nhat config
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
