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

REM === Bước 0.7: Cập nhật yt-dlp lên bản mới nhất ===
REM YouTube doi co che phat video gan nhu hang thang, con ban yt-dlp bi dong bang
REM trong .exe thi dung yen. Chi vai thang la client gap "Sign in to confirm
REM you're not a bot" roi "Requested format is not available" du cookie van dung.
REM Vi vay LUON build voi ban yt-dlp moi nhat.
echo ----------------------------------------
echo  Buoc 0.7: Cap nhat yt-dlp
echo ----------------------------------------
REM [default] keo theo yt-dlp-ejs: script giai "n challenge" cua YouTube, phai
REM nam san trong .exe vi may khach thuong khong co duong ra npm.
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
REM qjs.exe = runtime JavaScript cho yt-dlp (bat buoc tu cuoi 2025).
REM ffmpeg  = truoc day chi setup_all.bat tai ve; may cai loi mang la mat
REM           luon cham diem + do tone. Nay gong thang vao bo cai.
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
echo.
python sync_version.py
echo.


REM === Bước 2: Build EXE bằng PyInstaller ===
echo ----------------------------------------
echo  Buoc 2: Build EXE bang PyInstaller
echo ----------------------------------------
echo.

if not exist "QuangLuuStudio.spec" (
    echo [ERROR] Khong tim thay file QuangLuuStudio.spec!
    pause
    exit /b 1
)

if exist build rd /s /q build
if exist dist rd /s /q dist
PyInstaller QuangLuuStudio.spec --noconfirm
if %errorlevel% neq 0 (
    echo [LOI] PyInstaller that bai
    pause
    exit /b 1
)
if not exist "dist\QuangLuuStudio\QuangLuuStudio.exe" (
    echo [LOI] Khong thay dist\QuangLuuStudio\QuangLuuStudio.exe
    pause
    exit /b 1
)
for /f "delims=" %%V in ('python -c "from core.version import __version__;print(__version__)"') do set "QLS_VER=%%V"
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_velopack.ps1 -Version %QLS_VER% -OutputDir releases
if %errorlevel% neq 0 (
    echo [LOI] Dong goi Velopack that bai
    pause
    exit /b 1
)
"%ISCC_PATH%" /DVelopackDir=releases QuangLuuStudio_Bridge.iss
if %errorlevel% neq 0 (
    echo [LOI] Build bo cai cau noi that bai
    pause
    exit /b 1
)
echo.
echo [OK] releases\QuangLuuStudio-CaiDat.exe  (cai moi)
echo [OK] installer_output\Setup_QuangLuuStudio_v%QLS_VER%.exe  (cau noi cho may 1.8.x)
pause
