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

REM === Bước 3: Build Installer bằng Inno Setup ===
echo ----------------------------------------
echo  Buoc 3: Build Installer bang Inno Setup
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
echo  File cai dat: installer_output\Setup_QuangLuuStudio_v1.7.5.exe
echo.
echo  Ban co the gui file nay cho nguoi khac
echo  de ho cai dat Quang Luu Studio.
echo ========================================
echo.
pause
