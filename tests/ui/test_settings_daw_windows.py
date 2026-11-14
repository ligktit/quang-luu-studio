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


# ── Danh sách từng cửa sổ (plugin, ASIO) ─────────────────────────────────────

def _E(hwnd, title, is_main=False, visible=False, source="daw"):
    from core.so_windows import WindowEntry
    return WindowEntry(hwnd, title, is_main, visible, source)


_WINS = [_E(1, "Studio One - mau", is_main=True), _E(2, "Auto-Tune Pro"),
         _E(3, "ASIO Link Pro", visible=True, source="asio")]


def _refresh(dlg, wins=_WINS):
    with patch("core.so_windows.list_windows", return_value=list(wins)):
        dlg._refresh_daw_windows_ui()


def test_danh_sach_hien_dung_trang_thai(dlg):
    _refresh(dlg)
    assert set(dlg._window_switches) == {1, 2, 3}
    assert "(cửa sổ chính)" in dlg._window_switches[1].text()
    assert "Auto-Tune Pro" in dlg._window_switches[2].text()
    assert "ASIO" in dlg._window_switches[3].text()
    assert dlg._window_switches[2].isChecked() is False
    assert dlg._window_switches[3].isChecked() is True


def test_bat_cong_tac_chi_hien_cua_so_do(dlg):
    _refresh(dlg)
    with patch("core.so_windows.show_window", return_value=True) as show, \
         patch("core.so_windows.list_windows", return_value=_WINS):
        dlg._window_switches[2].click()
    show.assert_called_once_with(2, above_topmost=False)


def test_tat_cong_tac_an_cua_so_do(dlg):
    _refresh(dlg)
    with patch("core.so_windows.hide_window", return_value=True) as hide, \
         patch("core.so_windows.list_windows", return_value=_WINS):
        dlg._window_switches[3].click()
    hide.assert_called_once_with(3)


def test_app_dang_ghim_thi_dua_plugin_len_tren(dlg):
    dlg._dashboard.settings["always_on_top"] = True
    _refresh(dlg)
    with patch("core.so_windows.show_window", return_value=True) as show, \
         patch("core.so_windows.list_windows", return_value=_WINS):
        dlg._window_switches[2].click()
    show.assert_called_once_with(2, above_topmost=True)


def test_hwnd_chet_thi_bao_va_quet_lai(dlg):
    _refresh(dlg)
    with patch("core.so_windows.show_window", return_value=False), \
         patch("core.so_windows.list_windows", return_value=[_WINS[0]]) as lw, \
         patch.object(dlg._dashboard, "_show_message") as msg:
        dlg._window_switches[2].click()
    assert lw.call_count >= 1
    assert set(dlg._window_switches) == {1}
    assert "quét lại" in msg.call_args.args[0]


def test_daw_chua_chay_danh_sach_trong_co_giai_thich(dlg):
    _refresh(dlg, wins=[])
    assert dlg._window_switches == {}
    assert dlg._windows_empty_lbl.isVisibleTo(dlg)
    assert "không có cửa sổ" in dlg._windows_empty_lbl.text()


def test_lam_moi_va_hien_an_tat_ca_quet_lai(dlg):
    with patch("core.so_windows.list_windows", return_value=_WINS) as lw:
        dlg._btn_refresh_windows.click()
        assert lw.call_count == 1
        with patch.object(dlg._dashboard, "_on_toggle_studio_one"):
            dlg._btn_toggle_all.click()
        assert lw.call_count == 2


def test_bat_cong_tac_giu_cho_ban_phim(dlg):
    # KTV dùng phím Tab/Space đi qua danh sách: bật/tắt xong danh sách dựng lại,
    # chỗ đang chọn phải nằm lại đúng cửa sổ vừa bật, không văng ra ngoài.
    _refresh(dlg)
    dlg._window_switches[2].setFocus()
    with patch("core.so_windows.show_window", return_value=True), \
         patch("core.so_windows.list_windows", return_value=_WINS):
        dlg._window_switches[2].click()
    assert dlg.focusWidget() is dlg._window_switches[2]


def test_cua_so_vua_bat_bien_mat_thi_cho_ban_phim_ve_nut_lam_moi(dlg):
    _refresh(dlg)
    dlg._window_switches[2].setFocus()
    with patch("core.so_windows.show_window", return_value=False), \
         patch("core.so_windows.list_windows", return_value=[_WINS[0]]), \
         patch.object(dlg._dashboard, "_show_message"):
        dlg._window_switches[2].click()
    assert dlg.focusWidget() is dlg._btn_refresh_windows
