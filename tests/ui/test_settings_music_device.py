"""Cài đặt → Âm thanh: chọn thiết bị đưa nhạc vào DAW (Tự sửa âm thanh đặt lại về đây)."""
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


from core.audio_doctor.win_audio import Device

DEVICES = [Device("{spk}", "Speakers (Realtek)"), Device("{vad}", "ASIOVADPRO Out")]


def test_combo_liet_ke_thiet_bi_va_luu_id(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, settings={"music_playback_device_id": "{vad}"})
    with patch("core.audio_doctor.win_audio.WinAudio.render_devices", return_value=DEVICES):
        dlg = _open_dialog(qtbot, dashboard)
    combo = dlg._combo_music_dev
    assert combo.currentData() == "{vad}"
    combo.setCurrentIndex(combo.findData("{spk}"))
    _save_without_side_effects(dlg)
    assert dashboard.settings["music_playback_device_id"] == "{spk}"
    assert dashboard.settings["music_playback_device_name"] == "Speakers (Realtek)"


def test_thiet_bi_da_luu_khong_con_tren_may_van_giu(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, settings={"music_playback_device_id": "{gone}",
                                                 "music_playback_device_name": "VB-Cable"})
    with patch("core.audio_doctor.win_audio.WinAudio.render_devices", return_value=DEVICES):
        dlg = _open_dialog(qtbot, dashboard)
    assert dlg._combo_music_dev.currentData() == "{gone}"
    assert "không thấy" in dlg._combo_music_dev.currentText()
    _save_without_side_effects(dlg)
    assert dashboard.settings["music_playback_device_name"] == "VB-Cable"
