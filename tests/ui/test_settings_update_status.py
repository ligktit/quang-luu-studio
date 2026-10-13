"""Cài đặt → Cập nhật phần mềm: chỉ còn dòng trạng thái, không còn nút/hộp thoại cập nhật."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6.QtWidgets")

from frontend_qt import MainDashboard
from ui.dialogs.settings_dialog import SettingsDialog
from core.updater import velopack_updater as vu

A11Y_CFG = {
    "tts_enabled": False, "tts_engine": "sapi", "tts_voice": "", "tts_rate": 170,
    "voice_command_enabled": False, "voice_model": "small",
    "high_contrast": False, "focus_ring_thick": False, "font_scale": 1.0,
    "announce_focus": True, "announce_state": True,
}


@pytest.fixture(autouse=True)
def _khong_ghi_settings_that():
    with patch("frontend_qt.backend.ConfigManager.save_settings"):
        yield


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


def _open(qtbot, updater, settings_update="khong-dat"):
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("core.entitlements.is_premium", return_value=True), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard({"studio_one_path": "", "auto_close_studio_one": False})
        qtbot.addWidget(dashboard)
        if settings_update != "khong-dat":
            dashboard.settings["update"] = settings_update
        if dashboard._so_ready_watcher is not None:
            dashboard._so_ready_watcher.stop()
    with patch("core.entitlements.is_premium", return_value=True), \
         patch("frontend_qt.backend.AppConfig.get_accessibility", return_value=dict(A11Y_CFG)), \
         patch("core.updater.velopack_updater._updater", updater):
        dlg = SettingsDialog(dashboard)
    qtbot.addWidget(dlg)
    return dlg


def test_trang_thai_cap_nhat_ban_cho(qtbot, mock_engine):
    u = vu.BackgroundUpdater("u", lambda: True, manager_factory=lambda *_: None)
    u.state.pending = "9.9.9"
    dlg = _open(qtbot, u)
    assert "đã tải sẵn 9.9.9, sẽ dùng ở lần mở sau" in dlg._update_status_lbl.text()
    assert not hasattr(dlg, "_update_check_btn")


def test_trang_thai_cap_nhat_ban_khong_velopack(qtbot, mock_engine):
    dlg = _open(qtbot, None)
    assert "không tự cập nhật" in dlg._update_status_lbl.text()


def test_settings_update_null_khong_lam_hong_hop_thoai(qtbot, mock_engine):
    dlg = _open(qtbot, None, settings_update=None)
    assert dlg._update_status_lbl.text()
