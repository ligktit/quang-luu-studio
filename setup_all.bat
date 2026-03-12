@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
echo ========================================
echo   Quang Luu Studio - Cai dat day du
echo   loopMIDI + Surface + Ung dung
echo ========================================
echo.

REM ============================================
REM  BƯỚC 1: Kiểm tra và cài đặt loopMIDI
REM ============================================
echo ----------------------------------------
echo  Buoc 1: Kiem tra loopMIDI
echo ----------------------------------------

set "LOOPMIDI_EXE="

REM Tìm loopMIDI trong các vị trí phổ biến
if exist "%ProgramFiles%\Tobias Erichsen\loopMIDI\loopMIDI.exe" (
    set "LOOPMIDI_EXE=%ProgramFiles%\Tobias Erichsen\loopMIDI\loopMIDI.exe"
)
if exist "%ProgramFiles(x86)%\Tobias Erichsen\loopMIDI\loopMIDI.exe" (
    set "LOOPMIDI_EXE=%ProgramFiles(x86)%\Tobias Erichsen\loopMIDI\loopMIDI.exe"
)
if exist "%LOCALAPPDATA%\Programs\Tobias Erichsen\loopMIDI\loopMIDI.exe" (
    set "LOOPMIDI_EXE=%LOCALAPPDATA%\Programs\Tobias Erichsen\loopMIDI\loopMIDI.exe"
)

if "!LOOPMIDI_EXE!"=="" (
    echo [CHUA CAI] loopMIDI chua duoc cai dat.
    echo.
    echo Dang mo trang tai loopMIDI...
    start "" "https://www.tobias-erichsen.de/software/loopmidi.html"
    echo.
    echo Vui long tai va cai dat loopMIDI, sau do nhan phim bat ky...
    pause >nul
    echo.
    
    REM Tìm lại sau khi user đã cài
    if exist "%ProgramFiles%\Tobias Erichsen\loopMIDI\loopMIDI.exe" (
        set "LOOPMIDI_EXE=%ProgramFiles%\Tobias Erichsen\loopMIDI\loopMIDI.exe"
    )
    if exist "%ProgramFiles(x86)%\Tobias Erichsen\loopMIDI\loopMIDI.exe" (
        set "LOOPMIDI_EXE=%ProgramFiles(x86)%\Tobias Erichsen\loopMIDI\loopMIDI.exe"
    )
    if exist "%LOCALAPPDATA%\Programs\Tobias Erichsen\loopMIDI\loopMIDI.exe" (
        set "LOOPMIDI_EXE=%LOCALAPPDATA%\Programs\Tobias Erichsen\loopMIDI\loopMIDI.exe"
    )
    
    if "!LOOPMIDI_EXE!"=="" (
        echo [ERROR] Van chua tim thay loopMIDI.
        echo Vui long cai dat loopMIDI truoc roi chay lai file nay.
        pause
        exit /b 1
    )
)

echo [OK] Tim thay loopMIDI: !LOOPMIDI_EXE!
echo.

REM ============================================
REM  BƯỚC 2: Khởi động loopMIDI và tạo port
REM ============================================
echo ----------------------------------------
echo  Buoc 2: Tao MIDI port "QuangLuuMIDI"
echo ----------------------------------------

REM Kiểm tra loopMIDI đang chạy chưa
tasklist /FI "IMAGENAME eq loopMIDI.exe" 2>nul | find /I "loopMIDI.exe" >nul
if !errorlevel! neq 0 (
    echo [INFO] Dang khoi dong loopMIDI...
    start "" "!LOOPMIDI_EXE!"
    timeout /t 3 /nobreak >nul
)

echo [INFO] Dang cau hinh port QuangLuuMIDI...

REM Thêm port QuangLuuMIDI vào loopMIDI config (registry)
reg query "HKCU\Software\Tobias Erichsen\loopMIDI\Ports" /v "QuangLuuMIDI" >nul 2>&1
if !errorlevel! neq 0 (
    reg add "HKCU\Software\Tobias Erichsen\loopMIDI\Ports" /v "QuangLuuMIDI" /t REG_SZ /d "QuangLuuMIDI" /f >nul 2>&1
    
    if !errorlevel! equ 0 (
        echo [OK] Da them port QuangLuuMIDI vao cau hinh
        REM Khởi động lại loopMIDI để nhận port mới
        taskkill /F /IM loopMIDI.exe >nul 2>&1
        timeout /t 2 /nobreak >nul
        start "" "!LOOPMIDI_EXE!"
        timeout /t 3 /nobreak >nul
    ) else (
        echo [CANH BAO] Khong the tu dong tao port.
        echo Vui long tao port thu cong trong loopMIDI:
        echo   1. Mo loopMIDI tu system tray
        echo   2. Go "QuangLuuMIDI" vao o "New port-name"
        echo   3. Nhan nut "+" de tao port
        echo.
        echo Nhan phim bat ky sau khi da tao port...
        pause >nul
    )
) else (
    echo [OK] Port QuangLuuMIDI da ton tai
)

REM Cấu hình autostart cho loopMIDI
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "loopMIDI" /t REG_SZ /d "\"!LOOPMIDI_EXE!\" /autostart" /f >nul 2>&1
echo [OK] Da cau hinh loopMIDI tu dong chay khi khoi dong Windows
echo.

REM ============================================
REM  BƯỚC 3: Cài đặt Surface cho Studio One
REM ============================================
echo ----------------------------------------
echo  Buoc 3: Cai dat QuangLuuMIDI Surface
echo ----------------------------------------

set "SURFACE_DIR="
set "S1_VERSION="

REM Tìm Studio One (ưu tiên version mới nhất)
if exist "%APPDATA%\PreSonus\Studio One 7" (
    set "SURFACE_DIR=%APPDATA%\PreSonus\Studio One 7\User Devices\QuangLuuMIDI"
    set "S1_VERSION=7"
)
if "!SURFACE_DIR!"=="" (
    if exist "%APPDATA%\PreSonus\Studio One 6" (
        set "SURFACE_DIR=%APPDATA%\PreSonus\Studio One 6\User Devices\QuangLuuMIDI"
        set "S1_VERSION=6"
    )
)
if "!SURFACE_DIR!"=="" (
    if exist "%APPDATA%\PreSonus\Studio One 5" (
        set "SURFACE_DIR=%APPDATA%\PreSonus\Studio One 5\User Devices\QuangLuuMIDI"
        set "S1_VERSION=5"
    )
)

if "!SURFACE_DIR!"=="" (
    echo [CANH BAO] Khong tim thay Studio One.
    echo Vui long cai dat Studio One truoc, roi chay lai file nay.
    echo.
    goto :skip_surface
)

echo [OK] Tim thay Studio One !S1_VERSION!
echo [INFO] Thu muc dich: !SURFACE_DIR!

REM Tạo thư mục nếu chưa có
if not exist "!SURFACE_DIR!" (
    mkdir "!SURFACE_DIR!"
    echo [OK] Da tao thu muc QuangLuuMIDI
)

REM Xác định thư mục nguồn (cùng folder với file .bat này)
set "SRC_DIR=%~dp0studio_one"

if not exist "!SRC_DIR!\QuangLuuMIDI.surface.xml" (
    echo [ERROR] Khong tim thay file surface tai: !SRC_DIR!
    echo Vui long kiem tra lai thu muc studio_one.
    pause
    goto :skip_surface
)

copy /Y "!SRC_DIR!\QuangLuuMIDI.surface.xml" "!SURFACE_DIR!\" >nul
copy /Y "!SRC_DIR!\deviceinfo.xml" "!SURFACE_DIR!\" >nul

REM Kiểm tra file đã copy thành công
if exist "!SURFACE_DIR!\QuangLuuMIDI.surface.xml" (
    echo [OK] Da copy QuangLuuMIDI.surface.xml
) else (
    echo [ERROR] Copy QuangLuuMIDI.surface.xml that bai!
)
if exist "!SURFACE_DIR!\deviceinfo.xml" (
    echo [OK] Da copy deviceinfo.xml
) else (
    echo [ERROR] Copy deviceinfo.xml that bai!
)

echo.
echo [QUAN TRONG] Vui long KHOI DONG LAI Studio One
echo de nhan dien QuangLuuMIDI Surface.

:skip_surface
echo.

REM ============================================
REM  BƯỚC 4: Cài đặt FFmpeg (cho YouTube)
REM ============================================
echo ----------------------------------------
echo  Buoc 4: Kiem tra FFmpeg
echo ----------------------------------------

REM Kiểm tra FFmpeg đã có chưa (cả PATH lẫn %LOCALAPPDATA%\FFmpeg)
where ffmpeg >nul 2>&1
if !errorlevel! equ 0 (
    echo [OK] FFmpeg da duoc cai dat ^(trong PATH^)
    goto :skip_ffmpeg
)

set "FFMPEG_DIR=%LOCALAPPDATA%\FFmpeg"
if exist "!FFMPEG_DIR!\ffmpeg.exe" (
    echo [OK] FFmpeg da co tai: !FFMPEG_DIR!
    goto :ffmpeg_ensure_path
)

echo [CHUA CAI] FFmpeg chua duoc cai dat.
echo FFmpeg can thiet de tai va phan tich audio tu YouTube.
echo.

set "FFMPEG_ZIP=%TEMP%\ffmpeg.zip"

REM URL 1: GitHub BtbN builds (stable)
set "FFMPEG_URL_1=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
REM URL 2: gyan.dev essentials (fallback)
set "FFMPEG_URL_2=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

set "DOWNLOAD_OK=0"

echo [INFO] Dang tai FFmpeg tu GitHub... (co the mat 1-2 phut)
powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%FFMPEG_URL_1%' -OutFile '%FFMPEG_ZIP%' -UseBasicParsing -TimeoutSec 120; Write-Host 'OK' } catch { Write-Host 'FAIL' }" 2>nul | find "OK" >nul

if !errorlevel! equ 0 (
    set "DOWNLOAD_OK=1"
    echo [OK] Tai tu GitHub thanh cong
) else (
    echo [CANH BAO] Tai tu GitHub that bai. Thu link du phong...
    echo [INFO] Dang tai FFmpeg tu gyan.dev...
    powershell -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%FFMPEG_URL_2%' -OutFile '%FFMPEG_ZIP%' -UseBasicParsing -TimeoutSec 120; Write-Host 'OK' } catch { Write-Host 'FAIL' }" 2>nul | find "OK" >nul
    
    if !errorlevel! equ 0 (
        set "DOWNLOAD_OK=1"
        echo [OK] Tai tu gyan.dev thanh cong
    )
)

if "!DOWNLOAD_OK!"=="0" (
    echo [ERROR] Khong the tai FFmpeg tu dong tu ca 2 nguon.
    echo.
    echo Ban co the tai thu cong bang cach:
    echo   1. Mo link: https://www.gyan.dev/ffmpeg/builds/
    echo   2. Tai "ffmpeg-release-essentials.zip"
    echo   3. Giai nen va copy ffmpeg.exe vao: %LOCALAPPDATA%\FFmpeg\
    echo.
    echo Nhan phim bat ky de tiep tuc...
    pause >nul
    goto :skip_ffmpeg
)

REM Giải nén
echo [INFO] Dang giai nen FFmpeg...
if not exist "!FFMPEG_DIR!" mkdir "!FFMPEG_DIR!"

powershell -Command "try { $ProgressPreference = 'SilentlyContinue'; Expand-Archive -Path '%FFMPEG_ZIP%' -DestinationPath '%TEMP%\ffmpeg_extract' -Force; $bin = Get-ChildItem -Path '%TEMP%\ffmpeg_extract' -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1; Copy-Item (Join-Path $bin.DirectoryName '*.exe') '%FFMPEG_DIR%\' -Force; Write-Host 'OK' } catch { Write-Host 'FAIL' }" 2>nul | find "OK" >nul

if !errorlevel! neq 0 (
    echo [ERROR] Giai nen FFmpeg that bai.
    echo Vui long tai va cai dat thu cong tai: https://www.gyan.dev/ffmpeg/builds/
    goto :skip_ffmpeg
)

echo [OK] Da giai nen FFmpeg vao: !FFMPEG_DIR!

REM Dọn file tạm
del "%FFMPEG_ZIP%" >nul 2>&1
rd /s /q "%TEMP%\ffmpeg_extract" >nul 2>&1

REM Kiểm tra FFmpeg hoạt động
"!FFMPEG_DIR!\ffmpeg.exe" -version >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] FFmpeg da giai nen nhung khong chay duoc.
    echo Vui long tai lai thu cong tai: https://www.gyan.dev/ffmpeg/builds/
    goto :skip_ffmpeg
)

echo [OK] FFmpeg hoat dong chinh thuong

:ffmpeg_ensure_path
REM Thêm vào PATH (cho user hiện tại) nếu chưa có
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "CURRENT_PATH=%%B"
echo !CURRENT_PATH! | find /I "FFmpeg" >nul
if !errorlevel! neq 0 (
    setx PATH "!CURRENT_PATH!;!FFMPEG_DIR!" >nul 2>&1
    set "PATH=!PATH!;!FFMPEG_DIR!"
    echo [OK] Da them FFmpeg vao PATH
) else (
    echo [OK] FFmpeg da co trong PATH
)

:skip_ffmpeg
echo.

REM ============================================
REM  HOÀN TẤT
REM ============================================
echo ========================================
echo          CAI DAT HOAN TAT!
echo ========================================
echo.
echo  Buoc tiep theo trong Studio One:
echo  1. DONG va MO LAI Studio One
echo  2. Options ^> External Devices ^> Add
echo  3. Tim "QuangLuuStudio" trong danh sach
echo  4. Chon "QuangLuuMIDI"
echo  5. Receive From: QuangLuuMIDI (loopMIDI)
echo  6. Dung Control Link de gan controls
echo.
pause

endlocal
