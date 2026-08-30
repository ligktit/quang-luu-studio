"""Phân biệt "bản Light đúng thiết kế" với "bản Heavy nạp QtWebEngine hỏng".

Hai ca này cùng cho `embedded_player_available() == False` nhưng chữa khác hẳn
nhau, và còn quyết định app tự tải file cài nào khi cập nhật
(`core/updater/_version_check.py`) — nhận nhầm là đẩy khách sang bản Light vĩnh
viễn.
"""
import importlib
import sys
from unittest.mock import patch

import pytest

from core import capabilities


def _nap_lai_voi_loi(exc):
    """Nạp lại core.capabilities với QtWebEngineWidgets ném `exc`."""
    that = __import__

    def gia(name, *a, **kw):
        if name == "PySide6.QtWebEngineWidgets":
            raise exc
        return that(name, *a, **kw)

    sys.modules.pop("core.capabilities", None)
    try:
        with patch("builtins.__import__", side_effect=gia):
            return importlib.import_module("core.capabilities")
    finally:
        sys.modules.pop("core.capabilities", None)
        importlib.import_module("core.capabilities")


def test_ban_light_nhan_ra_dung():
    mod = _nap_lai_voi_loi(
        ModuleNotFoundError("No module named 'PySide6.QtWebEngineWidgets'"))
    assert mod.embedded_player_available() is False
    assert mod.build_variant() == "Light"
    assert "Ban Light" in mod.describe()


def test_ban_heavy_hong_khong_bi_nham_la_ban_light():
    """DLL bị phần mềm diệt virus cách ly — máy VẪN là bản Heavy."""
    mod = _nap_lai_voi_loi(
        ImportError("DLL load failed while importing QtWebEngineCore"))
    assert mod.embedded_player_available() is False
    assert "Ban Light" not in mod.describe()
    assert "that bai" in mod.describe()
    assert "DLL load failed" in mod.embedded_player_error()


def test_khong_de_lot_ngoai_le_la_ra_ngoai():
    """Chỉ bắt ImportError là để lọt OSError/RuntimeError ra ngoài, dựng luôn
    dialog Thiết lập (nơi gọi `from core import capabilities` không bọc try)."""
    mod = _nap_lai_voi_loi(OSError("khong mo duoc Qt6WebEngineCore.dll"))
    assert mod.embedded_player_available() is False
    assert "OSError" in mod.embedded_player_error()


def test_nap_duoc_thi_khong_co_thong_diep_loi():
    if not capabilities.embedded_player_available():
        pytest.skip("moi truong nay khong co QtWebEngine")
    assert capabilities.embedded_player_error() == ""
    assert capabilities.build_variant() == "Heavy"
    assert "Heavy" in capabilities.describe()
