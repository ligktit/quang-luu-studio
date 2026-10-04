"""Cài đặt: chọn DAW ghi vào settings["daw_kind"], nhãn theo DAW đang chọn."""
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6.QtWidgets")

from core import daw
from frontend_qt import MainDashboard
from ui.dialogs.settings_dialog import SettingsDialog

A11Y_CFG = {
    "tts_enabled": False, "tts_engine": "sapi", "tts_voice": "", "tts_rate": 170,
    "voice_command_enabled": False, "voice_model": "small",
    "high_contrast": False, "focus_ring_thick": False, "font_scale": 1.0,
    "announce_focus": True, "announce_state": True,
}


@pytest.fixture(autouse=True)
def _khong_ghi_settings_that():
    """Dashboard ghi settings lúc đóng/đổi cấu hình; chặn ghi vào settings.json thật
    suốt cả test (kể cả lúc qtbot dọn widget)."""
    with patch("frontend_qt.backend.ConfigManager.save_settings"):
        yield


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


def test_auto_launch_dung_duoi_cpr_khi_cubase():
    self = MagicMock()
    self.settings = {"daw_kind": "cubase", "studio_one_path": r"D:\QLS\mau.cpr",
                     "auto_launch_studio_one": True, "auto_launch_browser": False}
    daw.bind(self.settings)
    try:
        with patch("core.kiosk.is_enabled", return_value=True), \
             patch("core.kiosk.restore_template_enabled", return_value=True), \
             patch("core.kiosk.is_locked", return_value=False), \
             patch("core.so_windows.is_running", return_value=False), \
             patch("core.so_template.has_template", return_value=True), \
             patch("core.so_template.restore", return_value={"restored": True, "reason": ""}) as restore, \
             patch("os.path.exists", return_value=True):
            MainDashboard._auto_launch_apps(self)
        restore.assert_called_once_with(r"D:\QLS\mau.cpr")
        self.engine.launch_app.assert_called_once_with(r"D:\QLS\mau.cpr")
    finally:
        daw.bind(None)


def test_settings_dialog_luu_daw_kind(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, settings={"daw_kind": "studio_one"})
    try:
        dlg = _open_dialog(qtbot, dashboard)
        idx = dlg._cmb_daw.findData("cubase")
        assert idx >= 0
        dlg._cmb_daw.setCurrentIndex(idx)
        assert dlg._collect_daw_kind() == "cubase"
        assert dlg._cb_launch_so.text() == "Mở Cubase khi khởi động"
        _save_without_side_effects(dlg)
        assert dashboard.settings["daw_kind"] == "cubase"
    finally:
        daw.bind(None)


def test_doi_daw_lam_moi_scale_values(qapp, mock_engine, qtbot):
    import frontend_qt
    old = frontend_qt.SCALE_VALUES
    dashboard = _make_dashboard(qtbot, settings={"daw_kind": "studio_one"})
    try:
        dlg = _open_dialog(qtbot, dashboard)
        dlg._cmb_daw.setCurrentIndex(dlg._cmb_daw.findData("cubase"))
        _save_without_side_effects(dlg)
        assert frontend_qt.SCALE_VALUES == {"major": 43, "minor": 85}
    finally:
        frontend_qt.SCALE_VALUES = old
        daw.bind(None)
