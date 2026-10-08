@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
REM ============================================
REM  CHE DO TU DONG: setup_all.bat /auto
REM  Bo cai (QuangLuuStudio_Setup.iss, [Code] ChayCaiDatTuDong) goi voi quyen
REM  nguoi dung goc sau khi chep file. Khong dung cho bam phim, bo buoc FFmpeg
REM  (bo cai da kem san), ghi toan bo man hinh ra
REM    %APPDATA%\QuangLuuStudio\logs\setup_all.txt
REM  Ma thoat la tong cac bit: 1 = chua du cong MIDI, 2 = chep script Cubase loi,
REM  4 = Cubase dang chay (phai Reload Scripts). 0 = xong, khong con viec gi.
REM ============================================
set "QLS_AUTO=0"
if /i "%~1"=="/auto" set "QLS_AUTO=1"
if /i "%~1"=="-auto" set "QLS_AUTO=1"
set "QLS_LOI=0"
if "!QLS_AUTO!"=="1" if not "%~2"=="log" (
    if not exist "%APPDATA%\QuangLuuStudio\logs" mkdir "%APPDATA%\QuangLuuStudio\logs"
    call "%~f0" /auto log > "%APPDATA%\QuangLuuStudio\logs\setup_all.txt" 2>&1
    exit /b !errorlevel!
)
echo ========================================
echo   Quang Luu Studio - Cai dat day du
echo   loopMIDI + Surface + Ung dung
if "!QLS_AUTO!"=="1" echo   ^(che do tu dong - %DATE% %TIME%^)
echo ========================================
echo.

REM ============================================
REM  BƯỚC 1: loopMIDI và các cổng MIDI ảo
REM ============================================
REM  Cả phần cài loopMIDI lẫn tạo cổng nằm trong setup_midi_ports.ps1:
REM  script đó tạo xong còn ĐẾM LẠI danh sách cổng MIDI thật sự có trên
REM  máy, thiếu thì mở loopMIDI lên chỉ cách thêm tay. Batch không làm
REM  được bước kiểm chứng đó.
echo ----------------------------------------
echo  Buoc 1: loopMIDI + cong QuangLuuMIDI, QLS_PhanHoi
echo ----------------------------------------
set "QLS_PS_ARGS="
if "!QLS_AUTO!"=="1" set "QLS_PS_ARGS=-NoPause"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_midi_ports.ps1" !QLS_PS_ARGS!
if !errorlevel! neq 0 (
    echo [CANH BAO] Chua tao du cong MIDI - xem huong dan o tren.
    set /a QLS_LOI+=1
)
echo.

REM ============================================
REM  BƯỚC 2: Cài đặt Surface cho Studio One
REM ============================================
echo ----------------------------------------
echo  Buoc 2: Cai dat QuangLuuMIDI Surface
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
    if "!QLS_AUTO!"=="0" pause
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
REM  BƯỚC 2b: Script MIDI Remote cho Cubase (12+)
REM ============================================
REM  Đúc kết từ ba máy khách (2026-10-06..08): script cũ trên máy có thể đã
REM  được sửa tay -> sao lưu .bak trước khi ghi đè; Cubase đang chạy thì phải
REM  Reload Scripts; Scale cho Auto-Tune Pro do script tự quy đổi, KHÔNG cần
REM  cân chỉnh từng máy nữa. Hướng dẫn đầy đủ: cubase\HUONG_DAN_CAI_DAT_CUBASE.md
echo ----------------------------------------
echo  Buoc 2b: Script MIDI Remote cho Cubase
echo ----------------------------------------
set "CB_FOUND="
for /d %%D in ("%ProgramFiles%\Steinberg\Cubase*") do set "CB_FOUND=%%~fD"
if "!CB_FOUND!"=="" for /d %%D in ("%APPDATA%\Steinberg\Cubase*") do set "CB_FOUND=%%~fD [prefs]"
if "!CB_FOUND!"=="" (
    echo [INFO] Khong thay Cubase trong Program Files hay AppData - bo qua ^(chi can khi dung Cubase^).
    goto :skip_cubase
)
echo [OK] Tim thay !CB_FOUND!
set "CB_SRC=%~dp0cubase\QuangLuu_QuangLuuMIDI.js"
if not exist "!CB_SRC!" (
    echo [ERROR] Thieu file !CB_SRC! - bo cai bi thieu thu muc cubase.
    goto :skip_cubase
)
REM Thu muc Documents THAT (OneDrive co the doi cho) - Cubase quet o day.
set "QLS_DOCS="
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "[Environment]::GetFolderPath([Environment+SpecialFolder]::MyDocuments)"`) do set "QLS_DOCS=%%P"
if "!QLS_DOCS!"=="" set "QLS_DOCS=%USERPROFILE%\Documents"
set "CB_DST=!QLS_DOCS!\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI"
if not exist "!CB_DST!" mkdir "!CB_DST!"
if exist "!CB_DST!\QuangLuu_QuangLuuMIDI.js" (
    fc /b "!CB_SRC!" "!CB_DST!\QuangLuu_QuangLuuMIDI.js" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] Script tren may da dung ban di kem, khong can chep lai.
        goto :cubase_sau_chep
    )
    copy /Y "!CB_DST!\QuangLuu_QuangLuuMIDI.js" "!CB_DST!\QuangLuu_QuangLuuMIDI.js.bak" >nul
    echo [OK] Da sao luu ban cu tren may -^> QuangLuu_QuangLuuMIDI.js.bak
)
copy /Y "!CB_SRC!" "!CB_DST!\" >nul
fc /b "!CB_SRC!" "!CB_DST!\QuangLuu_QuangLuuMIDI.js" >nul 2>&1
if !errorlevel! neq 0 (
    echo [ERROR] Copy script Cubase that bai! Dich: !CB_DST!
    set /a QLS_LOI+=2
    goto :skip_cubase
)
echo [OK] Da chep QuangLuu_QuangLuuMIDI.js -^> !CB_DST!
:cubase_sau_chep
for /f "tokens=2 delims='" %%V in ('findstr /c:"var QLS_SCRIPT_VERSION" "!CB_SRC!"') do echo [INFO] Phien ban script: %%V
tasklist /fi "imagename eq Cubase*" 2>nul | find /i "Cubase" >nul
if !errorlevel! equ 0 (
    echo [QUAN TRONG] Cubase DANG CHAY: Studio ^> MIDI Remote Manager ^> Scripts ^> Reload Scripts, hoac mo lai Cubase.
    set /a QLS_LOI+=4
) else (
    echo [OK] Cubase se tu nap script khi mo ^(can du 2 cong QuangLuuMIDI + QLS_PhanHoi o Buoc 1^).
)
echo [LUU Y] Studio ^> Studio Setup ^> Audio System: TAT "Release Driver when Application is in Background".
echo [LUU Y] Bai mau .cpr: track 1 = NHAC, track 2 = MIC/GIONG ^(Auto-Tune hoac Pitch Correct o insert 1^), kenh vang ten co chu Vang/Delay/Reverb.
echo [LUU Y] Trong app: Thiet lap ^> Phan mem thu am ^(DAW^) = Cubase, bai mau = file .cpr. Khong can can chinh Scale cho Auto-Tune Pro.
echo [LUU Y] Huong dan day du: %~dp0cubase\HUONG_DAN_CAI_DAT_CUBASE.md
:skip_cubase
echo.

REM ============================================
REM  BƯỚC 3: Cài đặt FFmpeg (cho YouTube)
REM ============================================
echo ----------------------------------------
echo  Buoc 3: Kiem tra FFmpeg
echo ----------------------------------------
if "!QLS_AUTO!"=="1" (
    echo [INFO] Che do tu dong: bo qua - bo cai da kem FFmpeg trong thu muc cai ^(ffmpeg\^).
    goto :skip_ffmpeg
)

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
echo  6. Send To: QLS_PhanHoi  (KHONG chon QuangLuuMIDI - se thanh vong lap)
echo  7. Dung Control Link de gan controls
echo.
if "!QLS_AUTO!"=="1" (
    echo [TU DONG] Ma thoat: !QLS_LOI! ^(0 = xong; 1 = thieu cong MIDI; 2 = script Cubase loi; 4 = Cubase dang chay, can Reload^)
) else (
    pause
)

endlocal & exit /b %QLS_LOI%
