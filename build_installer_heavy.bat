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

REM === Bước 0.5: Canh bao neu co thu muc la trong installer_output ===
REM installer_output CHI duoc chua file Setup_*.exe do Inno Setup xuat ra.
REM Da tung co ca ban sao project bi copy nham vao day (30-04-2026, 107 MB rac).
if exist "installer_output" (
    for /d %%D in ("installer_output\*") do (
        echo [ERROR] Phat hien thu muc la trong installer_output: %%~nxD
        echo         Thu muc nay CHI duoc chua file Setup_*.exe.
        echo         Neu do la ban sao project bi copy nham, hay xoa no roi build lai.
        echo.
        pause
        exit /b 1
    )
)

REM === Bật biến thể HEAVY cho spec (bundle QtWebEngine) ===
set "QLS_WEBENGINE=1"

REM === Bước 0.7: Cập nhật yt-dlp lên bản mới nhất ===
REM Xem ghi chu trong build_installer.bat: ban yt-dlp cu la nguyen nhan so 1
REM khien may khach khong tai / do tone duoc video YouTube.
echo ----------------------------------------
echo  Buoc 0.7: Cap nhat yt-dlp
echo ----------------------------------------
REM [default] keo theo yt-dlp-ejs - xem ghi chu trong build_installer.bat.
python -m pip install --upgrade --quiet "yt-dlp[default]"
if %errorlevel% neq 0 (
    echo [ERROR] Khong cap nhat duoc yt-dlp - kiem tra ket noi mang.
    pause
    exit /b 1
)
python -c "import yt_dlp;print('[OK] yt-dlp',yt_dlp.version.__version__)"
python -c "from yt_dlp.dependencies import yt_dlp_ejs;import sys;sys.exit(0 if yt_dlp_ejs else 1)"
if %errorlevel% neq 0 (
    echo [ERROR] Thieu yt-dlp-ejs - yt-dlp se phai tai script tu npm luc chay.
    pause
    exit /b 1
)
echo [OK] yt-dlp-ejs co san (giai n challenge offline)
echo.

REM === Bước 0.8: Tai binary phu tro (qjs.exe + ffmpeg) ===
echo ----------------------------------------
echo  Buoc 0.8: Tai binary phu tro
echo ----------------------------------------
python tools\fetch_build_binaries.py
if %errorlevel% neq 0 (
    echo [ERROR] Khong tai duoc binary phu tro - kiem tra ket noi mang.
    pause
    exit /b 1
)
echo.

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
echo  File cai dat: installer_output\Setup_QuangLuuStudio_Heavy_v1.7.4.exe
echo ========================================
echo.
pause
