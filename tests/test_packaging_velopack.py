"""Đóng gói Velopack: spec onedir, script pack chép đủ tài nguyên cạnh exe."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*p):
    with open(os.path.join(ROOT, *p), "rb") as f:
        return f.read().decode("utf-8-sig")


def test_spec_onedir_co_collect():
    spec = _read("QuangLuuStudio.spec")
    assert re.search(r"exe = EXE\(\s*pyz,\s*a\.scripts,\s*\[\],\s*exclude_binaries=True,", spec)
    assert "coll = COLLECT(" in spec and "name='QuangLuuStudio'" in spec


def test_build_velopack_chep_du_tai_nguyen_nhu_bo_cai_cu():
    ps = _read("tools", "build_velopack.ps1")
    for f in ["app_icon.ico", "setup_all.bat", "setup_midi_ports.ps1", "configure_youtube_cookies.bat",
              "kiem_tra_tone.bat", "thu_tai_youtube.bat", "app_config.json", "binaries\\qjs.exe"]:
        assert f'"{f}"' in ps, f
    for src, dst in [("studio_one", "studio_one"), ("cubase", "cubase"), ("sfx", "sfx"),
                     ("models", "models"), ("tools\\piper", "tools\\piper"), ("binaries\\ffmpeg", "ffmpeg")]:
        assert f'@("{src}", "{dst}")' in ps, src


def test_build_velopack_dung_ten_va_co():
    ps = _read("tools", "build_velopack.ps1")
    assert "--packId QuangLuuStudio" in ps and '--packTitle "Quang Lưu Studio"' in ps
    assert "--mainExe QuangLuuStudio.exe" in ps and "--pre" in ps
    assert "QuangLuuStudio-CaiDat.exe" in ps


def test_build_velopack_co_bom():
    with open(os.path.join(ROOT, "tools", "build_velopack.ps1"), "rb") as f:
        assert f.read(3) == b"\xef\xbb\xbf"


def test_khong_con_bo_cai_inno_chinh():
    assert not os.path.exists(os.path.join(ROOT, "QuangLuuStudio_Setup.iss"))
    assert not os.path.exists(os.path.join(ROOT, "build_installer_heavy.bat"))
