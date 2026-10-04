"""Script Cubase phải đi theo bộ cài và bản đóng gói, như surface.xml của Studio One."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8", errors="replace") as f:
        return f.read()


def test_iss_chep_script_cubase():
    assert 'Source: "cubase\\QuangLuu_QuangLuuMIDI.js"; DestDir: "{app}\\cubase"' in _read("QuangLuuStudio_Setup.iss")


def test_spec_dong_goi_thu_muc_cubase():
    assert "('cubase', 'cubase')" in _read("QuangLuuStudio.spec")


def test_setup_all_cai_script_cubase():
    bat = _read("setup_all.bat")
    assert "MIDI Remote\\Driver Scripts\\Local\\QuangLuu\\QuangLuuMIDI" in bat
    assert "QuangLuu_QuangLuuMIDI.js" in bat


def test_chan_doan_kiem_cubase():
    ps = _read(os.path.join("tools", "chan_doan", "QLS_ChanDoan.ps1"))
    assert "ReleaseHardware" in ps
    assert "QuangLuu_QuangLuuMIDI.js" in ps
