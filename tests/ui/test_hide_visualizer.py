"""Ẩn/hiện dải visualizer (thanh phổ nhảy theo nhạc, gói Premium).

Ẩn ở đây là GỠ HẲN widget chứ không phải setVisible(False): dải này chạy timer
30fps và giữ một ref tới nguồn thu audio dùng chung (AudioPulse, đếm ref). Ẩn mà
vẫn để nó sống thì máy vẫn tốn CPU đúng như khi đang hiện — ẩn làm gì nữa.
"""
from unittest.mock import MagicMock, patch

import pytest

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


def _make_dashboard(qtbot, premium=True, settings=None):
    base = {"studio_one_path": "", "auto_close_studio_one": False}
    base.update(settings or {})
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("core.entitlements.is_premium", return_value=premium), \
         patch("frontend_qt.QTimer.start"):
        # settings đi vào qua tham số dựng, KHÔNG qua ConfigManager
        dashboard = MainDashboard(base)
        qtbot.addWidget(dashboard)
        if dashboard._so_ready_watcher is not None:
            dashboard._so_ready_watcher.stop()
        return dashboard


def test_mac_dinh_premium_thi_hien_dai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    with patch("core.entitlements.is_premium", return_value=True):
        dashboard._apply_visualizer_setting()
    assert dashboard._premium_viz is not None


def test_bo_tich_thi_go_han_dai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    with patch("core.entitlements.is_premium", return_value=True):
        dashboard._apply_visualizer_setting()
        assert dashboard._premium_viz is not None

        viz = dashboard._premium_viz
        with patch.object(viz, "stop", wraps=viz.stop) as stopped:
            dashboard.settings["show_visualizer"] = False
            dashboard._apply_visualizer_setting()

    assert dashboard._premium_viz is None
    # Quên stop() thì luồng thu loopback chạy mãi dù dải đã biến mất.
    stopped.assert_called_once()


def test_tich_lai_thi_dung_lai_dai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True,
                                settings={"show_visualizer": False})
    with patch("core.entitlements.is_premium", return_value=True):
        assert dashboard._premium_viz is None

        dashboard.settings["show_visualizer"] = True
        dashboard._apply_visualizer_setting()
    assert dashboard._premium_viz is not None


def test_dai_nam_tren_cung_than_cua_so(qapp, mock_engine, qtbot):
    # Bật lại giữa chừng phải chèn về ĐÚNG vị trí cũ (trên hàng Mixer/Mode/Tools),
    # chứ không rơi xuống đáy.
    dashboard = _make_dashboard(qtbot, premium=True,
                                settings={"show_visualizer": False})
    with patch("core.entitlements.is_premium", return_value=True):
        dashboard.settings["show_visualizer"] = True
        dashboard._apply_visualizer_setting()

    layout = dashboard._body_inner_layout
    assert layout.itemAt(0).widget() is dashboard._premium_viz


def test_goi_lai_nhieu_lan_khong_de_them_dai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    with patch("core.entitlements.is_premium", return_value=True):
        dashboard._apply_visualizer_setting()
        first = dashboard._premium_viz
        dashboard._apply_visualizer_setting()
        dashboard._apply_visualizer_setting()

    assert dashboard._premium_viz is first
    layout = dashboard._body_inner_layout
    widgets = [layout.itemAt(i).widget() for i in range(layout.count())]
    assert widgets.count(first) == 1


def test_go_hai_lan_khong_no(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    dashboard.settings["show_visualizer"] = False
    dashboard._apply_visualizer_setting()
    dashboard._apply_visualizer_setting()
    assert dashboard._premium_viz is None


def test_standard_thi_khong_bao_gio_co_dai(qapp, mock_engine, qtbot):
    # Ô tích bật cũng vô nghĩa với gói Standard — không có dải để hiện.
    dashboard = _make_dashboard(qtbot, premium=False,
                                settings={"show_visualizer": True})
    with patch("core.entitlements.is_premium", return_value=False):
        dashboard._apply_visualizer_setting()
    assert dashboard._premium_viz is None


def test_khong_doc_duoc_goi_thi_coi_nhu_khong_co_dai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True)
    with patch("core.entitlements.is_premium", side_effect=RuntimeError("hỏng")):
        assert dashboard._visualizer_enabled() is False


def test_rebuild_than_cua_so_khong_ro_ref_audio(qapp, mock_engine, qtbot):
    # Dev Mode dựng lại thân cửa sổ. Trước đây widget cũ bị layout xoá mà không
    # ai gọi stop() → ref AudioPulse rò thêm một nấc mỗi lần bật/tắt Dev Mode.
    dashboard = _make_dashboard(qtbot, premium=True)
    with patch("core.entitlements.is_premium", return_value=True):
        dashboard._apply_visualizer_setting()
        old = dashboard._premium_viz
        assert old is not None

        with patch.object(old, "stop", wraps=old.stop) as stopped:
            dashboard.refresh_ui()

    stopped.assert_called_once()
    assert dashboard._premium_viz is not old


def test_o_tich_trong_thiet_lap_luu_dung_khoa(qapp, mock_engine, qtbot):
    from ui.dialogs.settings_dialog import SettingsDialog
    dashboard = _make_dashboard(qtbot, premium=True)

    with patch("core.entitlements.is_premium", return_value=True):
        dlg = SettingsDialog(dashboard)
        qtbot.addWidget(dlg)
        assert dlg._cb_show_viz.isChecked() is True
        assert dlg._cb_show_viz.isEnabled() is True

        dlg._cb_show_viz.setChecked(False)
        with patch("frontend_qt.backend.ConfigManager.save_settings") as save, \
             patch.object(dashboard, "_apply_visualizer_setting") as apply_viz:
            dlg._save()

    saved = save.call_args.args[0]
    assert saved["show_visualizer"] is False
    apply_viz.assert_called_once()


def test_o_tich_bi_khoa_voi_goi_standard(qapp, mock_engine, qtbot):
    from ui.dialogs.settings_dialog import SettingsDialog
    dashboard = _make_dashboard(qtbot, premium=False)

    with patch("core.entitlements.is_premium", return_value=False):
        dlg = SettingsDialog(dashboard)
        qtbot.addWidget(dlg)

    assert dlg._cb_show_viz.isEnabled() is False
    assert "Premium" in dlg._cb_show_viz.text()
