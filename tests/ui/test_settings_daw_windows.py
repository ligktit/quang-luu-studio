"""Cài đặt → "Cửa sổ {DAW}": tự ẩn khi mở app, phục hồi bản mẫu, hiện/ẩn DAW."""
from unittest.mock import patch

import pytest

pytest.importorskip("PySide6.QtWidgets")

from tests.ui.test_settings_daw_kind import (  # noqa: F401 — fixture dùng chung
    _khong_ghi_settings_that, _make_dashboard, _open_dialog, mock_engine,
)


@pytest.fixture
def dlg(qapp, mock_engine, qtbot):
    with patch("core.daw_visibility.auto_hide", return_value=True), \
         patch("core.daw_visibility.restore_template_enabled", return_value=False), \
         patch("core.so_windows.any_visible", return_value=False):
        dashboard = _make_dashboard(qtbot)
        yield _open_dialog(qtbot, dashboard)


def test_muc_cua_so_daw_khong_con_pin(dlg):
    for attr in ("_btn_kiosk_pin", "_cb_kiosk", "_btn_kiosk_unlock", "_combo_session",
                 "_cb_keep_hidden"):
        assert not hasattr(dlg, attr), attr


def test_tick_tu_an_ghi_ngay(dlg):
    assert dlg._cb_auto_hide.isChecked() is True
    with patch("core.daw_visibility.set_auto_hide") as setter:
        dlg._cb_auto_hide.click()
    setter.assert_called_once_with(False)


def test_tick_phuc_hoi_ban_mau_ghi_ngay(dlg):
    assert dlg._cb_restore_tpl.isChecked() is False
    with patch("core.daw_visibility.set_restore_template") as setter:
        dlg._cb_restore_tpl.click()
    setter.assert_called_once_with(True)


def test_nut_hien_an_tat_ca_goi_dashboard_va_doi_chu(dlg):
    with patch("core.so_windows.any_visible", return_value=False):
        dlg._refresh_daw_windows_ui()
    assert dlg._btn_toggle_all.text().startswith("Hiện")
    with patch.object(dlg._dashboard, "_on_toggle_studio_one") as toggle, \
         patch("core.so_windows.any_visible", return_value=True):
        dlg._btn_toggle_all.click()
    toggle.assert_called_once()
    assert dlg._btn_toggle_all.text().startswith("Ẩn")
