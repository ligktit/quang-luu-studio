"""Thiết lập: "Lưu thiết lập" và "Đồng bộ đám mây" không được làm app đứng.

Vì sao có file này (2026-10-03):
  - Nút "Đồng bộ ngay" kẹt mãi ở "Đang đồng bộ...": worker gọi
    QTimer.singleShot từ thread Python thường, thread đó không có event loop
    nên timer không bao giờ nổ, kết quả không bao giờ về UI.
  - Mỗi lần bấm Lưu, app đứng vài giây: theme.apply() đè QSS cho cả ứng dụng
    dù không đổi gì về tương phản / cỡ chữ; bật player nhúng còn join thread
    watcher 3s ngay trên main thread.
  - Toast "Đã lưu thiết lập" vẽ lên dialog đang đóng → khách không thấy gì.
"""
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6.QtWidgets")

from frontend_qt import MainDashboard
from ui.dialogs.settings_dialog import SettingsDialog

A11Y_CFG = {
    "tts_enabled": False, "tts_engine": "sapi", "tts_voice": "", "tts_rate": 170,
    "voice_command_enabled": False, "voice_model": "small",
    "high_contrast": False, "focus_ring_thick": False, "font_scale": 1.0,
    "announce_focus": True, "announce_state": True,
}


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def mock_engine():
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = "http://yt.com"
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._youtube_watcher_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        yield eng


def _make_dashboard(qtbot, premium=True, settings=None):
    base = {"studio_one_path": "", "auto_close_studio_one": False}
    base.update(settings or {})
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("core.entitlements.is_premium", return_value=premium), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard(base)
        qtbot.addWidget(dashboard)
        if dashboard._so_ready_watcher is not None:
            dashboard._so_ready_watcher.stop()
        return dashboard


def _open_dialog(qtbot, dashboard, premium=True):
    with patch("core.entitlements.is_premium", return_value=premium), \
         patch("frontend_qt.backend.AppConfig.get_accessibility", return_value=dict(A11Y_CFG)):
        dlg = SettingsDialog(dashboard)
    qtbot.addWidget(dlg)
    return dlg


def _save_without_side_effects(dlg):
    """Chạy _save() nhưng không ghi file thật và không đụng player/visualizer."""
    d = dlg._dashboard
    with patch("frontend_qt.backend.ConfigManager.save_settings"), \
         patch("frontend_qt.backend.AppConfig.update"), \
         patch("frontend_qt.backend.AppConfig.save"), \
         patch("frontend_qt.backend.AppConfig.set_accessibility"), \
         patch.object(d, "_apply_embedded_player_setting"), \
         patch.object(d, "_apply_visualizer_setting"), \
         patch.object(d, "_apply_auto_echo_setting"), \
         patch.object(d, "_apply_auto_noise_setting"):
        dlg._save()


# ── Đồng bộ đám mây ──
def test_dong_bo_dam_may_tra_nut_ve_binh_thuong_khi_xong(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    dlg = _open_dialog(qtbot, dashboard, premium=True)
    btn = dlg._cloud_sync_btn

    done = {"ok": True, "results": {
        k: {"push": {"ok": True}, "pull": {"ok": True}}
        for k in ("songs", "timelines", "tones", "scores")
    }}
    with patch("core.entitlements.is_premium", return_value=True), \
         patch("core.licensing.sync.sync_all", return_value=done):
        btn.click()
        assert btn.isEnabled() is False
        assert btn.text() == "Đang đồng bộ..."
        qtbot.waitUntil(btn.isEnabled, timeout=3000)

    assert btn.text() == "Đồng bộ ngay"
    assert "4/4" in btn.toolTip()


def test_dong_bo_dam_may_bao_loi_de_doc_khi_mat_mang(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    dlg = _open_dialog(qtbot, dashboard, premium=True)
    btn = dlg._cloud_sync_btn
    offline = {"ok": True, "results": {
        k: {"push": {"ok": False, "error": "offline"}, "pull": {"ok": False, "error": "offline"}}
        for k in ("songs", "timelines", "tones", "scores")
    }}
    with patch("core.entitlements.is_premium", return_value=True), \
         patch("core.licensing.sync.sync_all", return_value=offline):
        btn.click()
        qtbot.waitUntil(btn.isEnabled, timeout=3000)

    assert "Không kết nối được máy chủ" in btn.toolTip()
    assert "{" not in btn.toolTip(), "không được hiện dict thô cho khách"


# ── Lưu thiết lập ──
def test_luu_khong_doi_giao_dien_thi_khong_ap_lai_theme(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    theme = MagicMock()
    theme.visual_settings.return_value = (False, False, 1.0)
    dashboard._a11y_theme = theme
    dlg = _open_dialog(qtbot, dashboard)

    _save_without_side_effects(dlg)

    theme.apply.assert_not_called()


def test_luu_doi_tuong_phan_thi_ap_theme_mot_lan(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    theme = MagicMock()
    theme.visual_settings.return_value = (False, False, 1.0)
    dashboard._a11y_theme = theme
    dlg = _open_dialog(qtbot, dashboard)

    dlg._a11y_cb_high_contrast.setChecked(True)
    _save_without_side_effects(dlg)

    theme.set_high_contrast.assert_called_with(True)
    theme.apply.assert_called_once()


def test_thong_bao_da_luu_hien_sau_khi_dialog_da_dong(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    dashboard._a11y_theme = None
    dlg = _open_dialog(qtbot, dashboard)
    dlg.show()
    qtbot.waitExposed(dlg)

    seen = []
    with patch.object(dashboard, "_show_message",
                      side_effect=lambda *a, **k: seen.append(dlg.isVisible())):
        _save_without_side_effects(dlg)

    assert seen == [False], "toast phải hiện khi dialog đã đóng, không thì vẽ lên cửa sổ đang biến mất"


def test_bat_player_nhung_khong_join_watcher_tren_main_thread(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True,
                                settings={"use_embedded_player": True})
    dashboard._player_window = None
    mock_engine.stop_youtube_watcher.reset_mock()
    with patch("core.capabilities.embedded_player_available", return_value=True), \
         patch.object(dashboard, "_create_player_window"), \
         patch.object(dashboard, "_wire_auto_tone_callbacks"):
        dashboard._apply_embedded_player_setting()

    mock_engine.stop_youtube_watcher.assert_called_once_with(wait=False)
