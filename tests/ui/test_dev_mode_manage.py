"""Nút ⚙ Quản lý trên panel + luồng lưu/nhập ở MainDashboard."""
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget

from ui.panels._dev_buttons import build_dev_row


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_hang_nut_dev_goi_dung_ham(qapp, qtbot):
    dash = MagicMock()
    host = QWidget()
    qtbot.addWidget(host)
    host.setLayout(build_dev_row(dash, "tools", "+ Thêm Nút", "button"))
    buttons = {b.text(): b for b in host.findChildren(QPushButton)}
    assert set(buttons) == {"+ Thêm Nút", "⚙ Quản lý"}
    buttons["+ Thêm Nút"].click()
    dash._on_add_widget.assert_called_once_with("tools", "button")
    buttons["⚙ Quản lý"].click()
    dash._on_manage_widgets.assert_called_once_with("tools")


# ── MainDashboard ──────────────────────────────────────────────
from frontend_qt import MainDashboard  # noqa: E402


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


@pytest.fixture
def dashboard(qapp, mock_engine, qtbot):
    base = {"studio_one_path": "", "auto_close_studio_one": False}
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        d = MainDashboard(base)
        qtbot.addWidget(d)
        if d._so_ready_watcher is not None:
            d._so_ready_watcher.stop()
        yield d


def _fake_manager(result, restored=False, calibrations=()):
    inst = MagicMock()
    inst.exec.return_value = result
    inst.restored = restored
    inst.calibrations = list(calibrations)
    return MagicMock(return_value=inst)


def test_dev_mode_co_nut_quan_ly_tren_3_panel(dashboard):
    dashboard.is_dev_mode = True
    dashboard.refresh_ui()
    manage = [b for b in dashboard.findChildren(QPushButton) if b.text() == "⚙ Quản lý"]
    assert len(manage) == 3


def test_luu_trong_hop_quan_ly_ap_calibration_va_ve_lai(dashboard):
    fake = _fake_manager(QDialog.Accepted, calibrations=[{"toggle_invert": {"be": True}}])
    with patch("ui.dialogs.widget_manager.WidgetManagerDialog", fake), \
         patch.object(dashboard, "_apply_widget_calibration") as apply_cal, \
         patch.object(dashboard, "refresh_ui") as refresh:
        dashboard._on_manage_widgets("tools")
    kwargs = fake.call_args.kwargs
    assert kwargs["panel_name"] == "tools"
    assert kwargs["engine"] is dashboard.engine
    apply_cal.assert_called_once_with({"toggle_invert": {"be": True}})
    refresh.assert_called_once()


def test_huy_hop_quan_ly_khong_lam_gi(dashboard):
    fake = _fake_manager(QDialog.Rejected)
    with patch("ui.dialogs.widget_manager.WidgetManagerDialog", fake), \
         patch.object(dashboard, "refresh_ui") as refresh:
        dashboard._on_manage_widgets("mixer")
    refresh.assert_not_called()


def test_nhap_file_xong_nap_lai_va_gui_lai_trang_thai(dashboard):
    fake = _fake_manager(QDialog.Accepted, restored=True)
    with patch("ui.dialogs.widget_manager.WidgetManagerDialog", fake), \
         patch.object(dashboard, "_apply_widget_calibration") as apply_cal, \
         patch.object(dashboard, "refresh_ui") as refresh, \
         patch.object(dashboard, "_resend_calibrated_states") as resend:
        dashboard._on_manage_widgets("mode")
    apply_cal.assert_not_called()  # file nhập đã ghi calibration — không ghi lại
    refresh.assert_called_once()
    modes, toggles = resend.call_args.args
    assert set(toggles) == {"tone_auto", "fix_meo", "be", "tat_on"}
    assert set(modes) == set(dashboard.mode_states)


def test_them_widget_truyen_engine_cho_builder(dashboard):
    inst = MagicMock()
    inst.exec.return_value = QDialog.Rejected
    fake = MagicMock(return_value=inst)
    with patch("ui.dialogs.widget_builder.WidgetBuilderDialog", fake):
        dashboard._on_add_widget("tools", "button")
    kwargs = fake.call_args.kwargs
    assert kwargs["engine"] is dashboard.engine
    assert kwargs["midi_cc"] is dashboard.MIDI_CC
    assert "tools" in kwargs["ui_config"]
