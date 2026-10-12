"""_cleanup_mei chỉ được xoá thư mục giải nén TẠM của onefile.

Bản onedir (Velopack) có sys._MEIPASS = <thư mục cài>\\_internal — xoá nó là
app tự huỷ mỗi lần thoát."""
import os
import sys
import tempfile

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
