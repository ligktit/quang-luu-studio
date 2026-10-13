"""Cài đặt → Công cụ: nút chẩn đoán gọi đúng .bat; Xoá dữ liệu chỉ hẹn xoá khi khách đồng ý."""
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt

pytest.importorskip("PySide6.QtWidgets")

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
    with patch("frontend_qt.backend.ConfigManager.save_settings"):
        yield


@pytest.fixture
def dlg(qtbot):
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = "http://yt.com"
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._youtube_watcher_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
             patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
             patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
             patch("core.entitlements.is_premium", return_value=True), \
             patch("frontend_qt.QTimer.start"):
            dashboard = MainDashboard({"studio_one_path": "", "auto_close_studio_one": False})
            qtbot.addWidget(dashboard)
            if dashboard._so_ready_watcher is not None:
                dashboard._so_ready_watcher.stop()
        with patch("core.entitlements.is_premium", return_value=True), \
             patch("frontend_qt.backend.AppConfig.get_accessibility", return_value=dict(A11Y_CFG)):
            d = SettingsDialog(dashboard)
        qtbot.addWidget(d)
        yield d


@pytest.mark.parametrize("attr,bat", [("_btn_kiem_tra_tone", "kiem_tra_tone.bat"),
                                      ("_btn_thu_tai", "thu_tai_youtube.bat")])
def test_nut_chan_doan_chay_dung_bat(dlg, attr, bat):
    with patch("core.app_tools.launch_bat", return_value=True) as launch:
        qtbot_click(getattr(dlg, attr))
    assert launch.call_args.args[1] == bat


def test_xoa_du_lieu_khong_dong_y_thi_khong_hen(dlg):
    with patch("ui.dialogs.settings_dialog._ask_wipe", return_value=(False, False)), \
         patch("core.app_tools.schedule_wipe_after_exit") as sched:
        qtbot_click(dlg._btn_xoa_du_lieu)
    sched.assert_not_called()


def test_xoa_du_lieu_dong_y_thi_hen_xoa(dlg):
    with patch("ui.dialogs.settings_dialog._ask_wipe", return_value=(True, True)), \
         patch("core.app_tools.wipe_targets", return_value=["X:\\QuangLuuStudio"]) as tg, \
         patch("core.app_tools.schedule_wipe_after_exit", return_value=True) as sched:
        qtbot_click(dlg._btn_xoa_du_lieu)
    assert tg.call_args.args[2] is True          # có tích "cả bản thu"
    sched.assert_called_once_with(["X:\\QuangLuuStudio"])
    assert "đóng app" in dlg._lbl_xoa_du_lieu.text()


@pytest.mark.parametrize("attr,bat", [("_btn_kiem_tra_tone", "kiem_tra_tone.bat"),
                                      ("_btn_thu_tai", "thu_tai_youtube.bat")])
def test_nut_bat_that_bai_thi_bao_loi(dlg, attr, bat):
    with patch("core.app_tools.launch_bat", return_value=False):
        qtbot_click(getattr(dlg, attr))
    assert f"Không mở được {bat}" in dlg._lbl_cong_cu.text()


def test_nut_bat_thanh_cong_thi_xoa_thong_bao(dlg):
    dlg._lbl_cong_cu.setText("cũ")
    with patch("core.app_tools.launch_bat", return_value=True):
        qtbot_click(dlg._btn_kiem_tra_tone)
    assert dlg._lbl_cong_cu.text() == ""


def test_mo_thu_muc_ban_thu_that_bai_thi_bao_loi(dlg):
    with patch("core.app_tools.open_folder", return_value=False):
        qtbot_click(dlg._btn_mo_ban_thu)
    assert "Không mở được thư mục bản thu" in dlg._lbl_cong_cu.text()


def test_xoa_du_lieu_khong_co_dich_thi_bao_loi_va_khong_hen(dlg):
    with patch("ui.dialogs.settings_dialog._ask_wipe", return_value=(True, False)), \
         patch("core.app_tools.wipe_targets", return_value=[]), \
         patch("core.app_tools.schedule_wipe_after_exit") as sched:
        qtbot_click(dlg._btn_xoa_du_lieu)
    sched.assert_not_called()
    assert "Không xoá được" in dlg._lbl_xoa_du_lieu.text()


def qtbot_click(btn):
    btn.click()
