"""_cleanup_mei chỉ được xoá thư mục giải nén TẠM của onefile.

Bản onedir (Velopack) có sys._MEIPASS = <thư mục cài>\\_internal — xoá nó là
app tự huỷ mỗi lần thoát."""
import os
import sys
import tempfile

import pytest

from core import frozen_paths


def test_khong_frozen_thi_none(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert frozen_paths.onefile_extract_dir() is None


def test_onefile_trong_temp_thi_tra_duong_dan(monkeypatch):
    mei = os.path.join(tempfile.gettempdir(), "_MEI123456")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", mei, raising=False)
    assert frozen_paths.onefile_extract_dir() == mei


def test_onedir_internal_thi_none(monkeypatch, tmp_path):
    internal = tmp_path / "QuangLuuStudio" / "current" / "_internal"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(internal), raising=False)
    assert frozen_paths.onefile_extract_dir() is None


def test_ten_mei_nhung_khong_nam_trong_temp_thi_none(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "x" / "_MEI99"), raising=False)
    assert frozen_paths.onefile_extract_dir() is None


@pytest.mark.skipif(sys.platform != "win32", reason="tên 8.3 chỉ có trên Windows")
def test_temp_dang_ten_ngan_8_3_van_nhan(monkeypatch, tmp_path):
    """%TEMP% có thể ở dạng 8.3 (C:\\Users\\GRANTT~1\\...) trong khi _MEIPASS dạng dài
    — hoặc ngược lại. Hai dạng phải được coi là cùng một thư mục."""
    import ctypes
    temp_long = tmp_path / "Thu Muc Tam Dai"
    mei = temp_long / "_MEI4242"
    mei.mkdir(parents=True)
    buf = ctypes.create_unicode_buffer(1024)
    ctypes.windll.kernel32.GetShortPathNameW(str(temp_long), buf, 1024)
    if not buf.value or buf.value == str(temp_long):
        pytest.skip("ổ đĩa không tạo tên 8.3 (fsutil 8dot3name) — không kiểm được")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: buf.value)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(mei), raising=False)
    assert frozen_paths.onefile_extract_dir() == str(mei)
