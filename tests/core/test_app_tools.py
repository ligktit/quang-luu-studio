"""Công cụ trong app thay shortcut .bat + xoá dữ liệu sau khi app thoát."""
import base64
import os

import pytest

from core import app_tools


def test_chay_bat_dung_cwd(tmp_path):
    app = tmp_path / "Nguyễn (A) & B"
    app.mkdir()
    (app / "kiem_tra_tone.bat").write_text("@echo off", encoding="ascii")
    calls = []
    assert app_tools.launch_bat(str(app), "kiem_tra_tone.bat",
                                popen=lambda args, **kw: calls.append((args, kw))) is True
    args, kw = calls[0]
    # tên .bat đứng một mình, thư mục qua cwd → ký tự ( ) & trong đường dẫn không vỡ lệnh cmd
    assert args == ["cmd.exe", "/c", "kiem_tra_tone.bat"]
    assert kw["cwd"] == str(app)


def test_chay_bat_thieu_file(tmp_path):
    assert app_tools.launch_bat(str(tmp_path), "khong_co.bat", popen=lambda *a, **k: None) is False


def test_mo_thu_muc(tmp_path):
    opened = []
    assert app_tools.open_folder(str(tmp_path), opener=opened.append) is True
    assert opened == [str(tmp_path)]
    assert app_tools.open_folder(str(tmp_path / "khong_co"), opener=opened.append) is False


def _dirs(tmp_path):
    data = tmp_path / "Roaming" / "QuangLuuStudio"
    rec = tmp_path / "Documents" / "QuangLuuStudio"
    data.mkdir(parents=True)
    rec.mkdir(parents=True)
    return str(data), str(rec)


def test_dich_xoa_mac_dinh_chi_du_lieu(tmp_path):
    data, rec = _dirs(tmp_path)
    assert app_tools.wipe_targets(data, rec, False, frozen=True) == [os.path.abspath(data)]
    assert app_tools.wipe_targets(data, rec, True, frozen=True) == [os.path.abspath(data), os.path.abspath(rec)]


def test_khong_xoa_khi_chay_tu_ma_nguon(tmp_path):
    data, rec = _dirs(tmp_path)
    assert app_tools.wipe_targets(data, rec, True, frozen=False) == []


@pytest.mark.parametrize("name", ["quang-luu-studio", "AppData", ""])
def test_khong_xoa_thu_muc_ten_la(tmp_path, name):
    d = tmp_path / name if name else tmp_path
    assert app_tools.wipe_targets(str(d), str(d), True, frozen=True) == []


def test_lenh_xoa_du_lieu_duong_dan_co_nhay_don():
    targets = [r"C:\Users\O'Brien Văn\AppData\Roaming\QuangLuuStudio"]
    cmd = app_tools.build_wipe_command(4242, targets)
    assert cmd[:4] == ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden"]
    assert cmd[4] == "-EncodedCommand"
    script = base64.b64decode(cmd[5]).decode("utf-16-le")
    assert "Wait-Process -Id 4242" in script
    assert r"Remove-Item -LiteralPath 'C:\Users\O''Brien Văn\AppData\Roaming\QuangLuuStudio' -Recurse -Force" in script


def test_hen_xoa_sau_khi_thoat(tmp_path):
    data, rec = _dirs(tmp_path)
    calls = []
    assert app_tools.schedule_wipe_after_exit([data], popen=lambda a, **k: calls.append((a, k)), pid=7) is True
    assert calls[0][0][0] == "powershell.exe"
    assert app_tools.schedule_wipe_after_exit([], popen=lambda a, **k: calls.append(a)) is False
