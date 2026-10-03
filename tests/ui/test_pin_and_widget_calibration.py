"""Nút ghim cửa sổ trên cùng + lưu Bypass/mode_config từ Dev Mode."""
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

from frontend_qt import MainDashboard


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
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        yield eng


def _make_dashboard(qtbot, settings=None):
    base = {"studio_one_path": "", "auto_close_studio_one": False}
    base.update(settings or {})
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard(base)
        qtbot.addWidget(dashboard)
        if dashboard._so_ready_watcher is not None:
            dashboard._so_ready_watcher.stop()
        return dashboard


def test_bam_ghim_luu_setting_va_dat_co(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard.show()
    with patch("frontend_qt.backend.ConfigManager.save_settings") as save:
        dashboard._on_toggle_always_on_top()
        assert dashboard.settings["always_on_top"] is True
        save.assert_called_once()
        assert dashboard.windowHandle().flags() & Qt.WindowStaysOnTopHint
        assert dashboard._pin_btn._active is True

        dashboard._on_toggle_always_on_top()
        assert dashboard.settings["always_on_top"] is False
        assert not (dashboard.windowHandle().flags() & Qt.WindowStaysOnTopHint)
        assert dashboard._pin_btn._active is False
    # Ghim không được ẩn cửa sổ (setWindowFlag trên QWidget sẽ làm vậy).
    assert dashboard.isVisible()


def test_mo_app_da_ghim_thi_tu_ghim_khi_hien(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, settings={"always_on_top": True})
    with patch.object(dashboard, "_set_always_on_top") as set_top:
        dashboard.show()
        qtbot.waitUntil(lambda: set_top.called, timeout=1000)
    set_top.assert_called_with(True)


def test_doi_bypass_nut_co_san_gui_lai_trang_thai(qapp, mock_engine, qtbot):
    from core.config import DEFAULT_TOGGLE_INVERT
    dashboard = _make_dashboard(qtbot)
    dashboard.be_state = False
    mock_engine.send_midi.reset_mock()
    invert = dict(DEFAULT_TOGGLE_INVERT, be=True)
    with patch("frontend_qt.backend.AppConfig.set_calibration", return_value=True) as setcal, \
         patch("frontend_qt.backend.AppConfig.get_toggle_invert", return_value=invert):
        dashboard._apply_widget_calibration({"toggle_invert": {"be": True}})
    setcal.assert_called_once_with(toggle_invert={"be": True})
    # Bè đang TẮT + Bypass → Studio One phải nhận Bypass On (127) ngay.
    be_cc = int(dashboard.MIDI_CC["be"])
    assert (be_cc, 127) in [c.args for c in mock_engine.send_midi.call_args_list]


def test_doi_mode_config_gui_lai_mode(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard.mode_states["Lofi"] = True
    mock_engine.send_midi.reset_mock()
    new_cfg = {"Lofi": {"cc": 37, "on_value": 0, "off_value": 127}}
    with patch("frontend_qt.backend.AppConfig.set_calibration", return_value=True), \
         patch.object(dashboard, "_get_mode_config", return_value=new_cfg):
        dashboard._apply_widget_calibration({"mode_config": new_cfg})
    assert (37, 0) in [c.args for c in mock_engine.send_midi.call_args_list]


def test_luu_calibration_loi_khong_gui_midi(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    mock_engine.send_midi.reset_mock()
    with patch("frontend_qt.backend.AppConfig.set_calibration", return_value=False):
        dashboard._apply_widget_calibration({"toggle_invert": {"be": True}})
    mock_engine.send_midi.assert_not_called()
