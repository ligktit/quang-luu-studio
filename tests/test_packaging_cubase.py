"""Script Cubase phải đi theo bộ cài và bản đóng gói, như surface.xml của Studio One."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8", errors="replace") as f:
        return f.read()


def test_spec_dong_goi_thu_muc_cubase():
    assert "('cubase', 'cubase')" in _read("QuangLuuStudio.spec")


def test_setup_all_cai_script_cubase():
    bat = _read("setup_all.bat")
    assert "MIDI Remote\\Driver Scripts\\Local\\QuangLuu\\QuangLuuMIDI" in bat
    assert "QuangLuu_QuangLuuMIDI.js" in bat
    # Ba máy khách: script trên máy có thể đã sửa tay → sao lưu trước khi ghi đè; Cubase đang chạy thì phải Reload.
    assert "QuangLuu_QuangLuuMIDI.js.bak" in bat
    assert 'tasklist /fi "imagename eq Cubase*"' in bat
    assert "Reload Scripts" in bat
    assert 'findstr /c:"var QLS_SCRIPT_VERSION"' in bat
    assert "HUONG_DAN_CAI_DAT_CUBASE.md" in bat
    # Tìm Cubase cả khi không nằm trong Program Files (prefs trong AppData).
    assert "%APPDATA%\\Steinberg\\Cubase*" in bat


def test_chan_doan_kiem_cubase():
    ps = _read(os.path.join("tools", "chan_doan", "QLS_ChanDoan.ps1"))
    assert "ReleaseHardware" in ps
    assert "QuangLuu_QuangLuuMIDI.js" in ps
    assert "QLS_SCRIPT_VERSION" in ps, "so phiên bản script trên máy với bản đi kèm app"
    # Tệp cân chỉnh kèm BOM bị app bỏ qua im lặng (máy 3, 2026-10-08) → chẩn đoán phải bắt được.
    assert "calibration_overrides.json" in ps and "0xEF" in ps and "0xBB" in ps and "0xBF" in ps


def test_setup_all_co_che_do_tu_dong():
    """Bộ cài chạy setup_all.bat /auto trong lúc cài: không được chờ bấm phím, phải báo kết quả bằng mã thoát."""
    bat = _read("setup_all.bat")
    assert 'if /i "%~1"=="/auto" set "QLS_AUTO=1"' in bat
    assert "-NoPause" in bat, "setup_midi_ports.ps1 có Read-Host nếu thiếu -NoPause"
    assert 'if "!QLS_AUTO!"=="0" pause' in bat
    assert "logs\\setup_all.txt" in bat
    assert "endlocal & exit /b %QLS_LOI%" in bat
    for bit in ("set /a QLS_LOI+=1", "set /a QLS_LOI+=2", "set /a QLS_LOI+=4"):
        assert bit in bat
    # Bước FFmpeg tải mạng không chạy ở chế độ tự động (bộ cài đã kèm ffmpeg\).
    assert bat.index('if "!QLS_AUTO!"=="1" (\n    echo [INFO] Che do tu dong: bo qua') < bat.index("FFMPEG_URL_1=")


def test_huong_dan_cubase_di_kem_ban_cai():
    # Quy trình cài đặt đi kèm bản cài (build_velopack.ps1 chép cả thư mục cubase\).
    assert os.path.exists(os.path.join(ROOT, "cubase", "HUONG_DAN_CAI_DAT_CUBASE.md"))
