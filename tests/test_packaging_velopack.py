"""Đóng gói Velopack: spec onedir, script pack chép đủ tài nguyên cạnh exe."""
import os
import re

import pytest

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


BATS_CHAY_TIEN_TRINH = ("setup_all.bat", "kiem_tra_tone.bat", "thu_tai_youtube.bat",
                        "configure_youtube_cookies.bat")


@pytest.mark.parametrize("name", BATS_CHAY_TIEN_TRINH)
def test_bat_roi_thu_muc_cai_truoc_moi_lenh(name):
    """App mở các .bat với CWD = thư mục cài (đường dẫn có ( ) & không vỡ dòng lệnh).
    cmd giữ CWD đó (console chờ "Press any key", loopMIDI do setup_all bật chạy mãi) thì
    Update.exe không đổi tên được thư mục cài → bản chờ không bao giờ được áp dụng."""
    lines = [ln.strip() for ln in _read(name).splitlines()]
    cd = next(i for i, ln in enumerate(lines) if ln.lower() == 'cd /d "%userprofile%"')
    first_cmd = next(i for i, ln in enumerate(lines)
                     if ln and not ln.lower().startswith(("@echo", "setlocal", "chcp", "rem", "title", "::"))
                     and i != cd)
    assert cd < first_cmd, f"{name}: cd /d \"%USERPROFILE%\" phải đứng trước dòng {first_cmd + 1}"


def test_spec_gom_dll_cua_vosk():
    """vosk nạp libvosk.dll từ thư mục của chính package (_internal\\vosk); thiếu thì lệnh
    giọng nói báo "vosk không khả dụng" trên bản cài."""
    spec = _read("QuangLuuStudio.spec")
    assert re.search(r"collect_dynamic_libs\(\s*['\"]vosk['\"]\s*\)", spec)
