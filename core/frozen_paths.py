"""Nhận biết kiểu đóng gói PyInstaller đang chạy."""
import os
import sys
import tempfile


def onefile_extract_dir():
    """Thư mục giải nén tạm của bản onefile (``%TEMP%\\_MEIxxxx``), hoặc None.

    Bản onedir cũng có ``sys._MEIPASS`` nhưng trỏ vào ``<thư mục cài>\\_internal``
    — thư mục đó là CHÍNH app, tuyệt đối không được xoá.
    """
    if not getattr(sys, "frozen", False):
        return None
    mei = getattr(sys, "_MEIPASS", None)
    if not mei:
        return None
    # realpath: %TEMP% và _MEIPASS có thể lệch dạng tên 8.3 (GRANTT~1) / tên dài.
    norm = os.path.normcase(os.path.realpath(mei))
    temp = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    if os.path.basename(norm).startswith(os.path.normcase("_MEI")) and os.path.dirname(norm) == temp:
        return mei
    return None
