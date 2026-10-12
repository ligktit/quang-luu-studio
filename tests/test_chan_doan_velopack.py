"""Bộ chẩn đoán phải tìm thấy bản cài Velopack (%LocalAppData%\\QuangLuuStudio\\current)."""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CD = os.path.join(ROOT, "tools", "chan_doan")
SCRIPTS = ["QLS_ChanDoan.ps1", "QLS_SuaLoi.ps1", "QLS_SuaManHinhNhung.ps1",
           "QLS_SuaPOToken.ps1", "KiemTraManHinhNhung.ps1"]


def _read(name):
    with open(os.path.join(CD, name), "rb") as f:
        raw = f.read()
    return raw, raw.decode("utf-8-sig")


@pytest.mark.parametrize("name", SCRIPTS)
def test_do_duong_dan_velopack_truoc_program_files(name):
    _, src = _read(name)
    i = src.find("QuangLuuStudio\\current")
    assert i != -1, "thiếu %LOCALAPPDATA%\\QuangLuuStudio\\current"
    j = src.find("ProgramFiles", src.rfind("\n", 0, i))
    assert i < j, "bản Velopack phải được dò trước Program Files"


@pytest.mark.parametrize("name", SCRIPTS)
def test_giu_bom_utf8(name):
    raw, src = _read(name)
    if re.search(r"[^\x00-\x7f]", src):
        assert raw.startswith(b"\xef\xbb\xbf")


def test_loai_tru_defender_tro_goc_velopack():
    _, src = _read("QLS_SuaManHinhNhung.ps1")
    assert "$exclRoot" in src and "Update.exe" in src
    assert "Add-MpPreference -ExclusionPath '\" + $exclRoot.Replace(" in src
