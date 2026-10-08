"""Thiết lập "Tắt hiệu ứng bắt mắt" (reduce_effects).

Một ô tích tắt mọi thứ chuyển động/nhấp nháy: dải visualizer, nút lấp lánh theo
nhạc (Premium), huy hiệu PREMIUM quét sáng, nháy viền ô tone, nút Ghi âm nhấp
nháy, nút SFX nhấp nháy đỏ khi thiếu file. Trạng thái vẫn phải thấy được (quầng
đỏ đứng yên khi đang ghi, viền đỏ đứng yên khi thiếu file) — chỉ bỏ chuyển động.
"""
from unittest.mock import MagicMock, patch

import pytest

from frontend_qt import MainDashboard
from ui.components.painter_button import PainterButton


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


# ── Từng component ──────────────────────────────────────────────────────────

def test_huy_hieu_premium_dung_quet_sang(qapp, qtbot):
    from ui.components.premium_tag import PremiumTag
    tag = PremiumTag("PREMIUM")
    qtbot.addWidget(tag)
    assert tag._timer.isActive()
    tag.set_animated(False)
    assert not tag._timer.isActive()
    tag.set_animated(True)
    assert tag._timer.isActive()


def test_nut_ghi_am_khong_nhap_nhay_nhung_van_sang(qapp, qtbot):
    from ui.components.painter_record import PainterRecordButton
    btn = PainterRecordButton()
    qtbot.addWidget(btn)
    btn.set_pulse_enabled(False)
    btn.set_recording(True)
    assert not btn._pulse_timer.isActive()
    assert btn._glow_opacity > 0.2          # vẫn báo đang ghi, chỉ không nhấp nháy
    btn.set_recording(False)
    assert btn._glow_opacity == 0.0


def test_nut_ghi_am_dang_ghi_thi_tat_nhap_nhay_ngay(qapp, qtbot):
    from ui.components.painter_record import PainterRecordButton
    btn = PainterRecordButton()
    qtbot.addWidget(btn)
    btn.set_recording(True)
    assert btn._pulse_timer.isActive()
    btn.set_pulse_enabled(False)
    assert not btn._pulse_timer.isActive() and btn._glow_opacity > 0.2
    btn.set_pulse_enabled(True)
    assert btn._pulse_timer.isActive()


def test_nut_sfx_thieu_file_vien_do_dung_yen(qapp, qtbot):
    from ui.components.sfx_button_area import SfxItemButton
    btn = SfxItemButton({"id": "x", "label": "Vỗ tay", "name": "Vỗ tay",
                         "file_path": "D:/khong/co/file.wav", "color": "#22c55e"})
    qtbot.addWidget(btn)
    assert btn._missing and btn._pulse_timer.isActive()
    btn.set_pulse_enabled(False)
    assert not btn._pulse_timer.isActive()
    assert btn._pulse_alpha >= 150           # viền đỏ rõ, không mờ dần
    btn.set_pulse_enabled(True)
    assert btn._pulse_timer.isActive()


# ── Dashboard ───────────────────────────────────────────────────────────────

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


def _reactive_buttons(dashboard):
    return [b for b in dashboard.findChildren(PainterButton) if b._music_reactive]


def test_tat_hieu_ung_thi_tat_het_ke_ca_premium(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True, settings={"reduce_effects": True})
    with patch("core.entitlements.is_premium", return_value=True):
        assert dashboard._visualizer_enabled() is False     # dù show_visualizer mặc định True
        dashboard._apply_effects_setting()
    assert dashboard._premium_viz is None
    assert _reactive_buttons(dashboard) == []
    assert not dashboard._premium_tag._timer.isActive()
    assert dashboard.tone_combo._flash_enabled is False
    assert dashboard.record_button._pulse_enabled is False


def test_bat_lai_hieu_ung_thi_premium_lap_lanh_lai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, premium=True, settings={"reduce_effects": True})
    with patch("core.entitlements.is_premium", return_value=True):
        dashboard.settings["reduce_effects"] = False
        dashboard._apply_effects_setting()
        dashboard._apply_visualizer_setting()
    assert _reactive_buttons(dashboard)
    assert dashboard._premium_tag._timer.isActive()
    assert dashboard.tone_combo._flash_enabled is True
    assert dashboard.record_button._pulse_enabled is True
    assert dashboard._premium_viz is not None


def test_dung_lai_than_cua_so_van_giu_tat_hieu_ung(qapp, mock_engine, qtbot):
    # Dev Mode dựng lại mọi nút → nút mới cũng không được lấp lánh.
    dashboard = _make_dashboard(qtbot, premium=True, settings={"reduce_effects": True})
    with patch("core.entitlements.is_premium", return_value=True):
        dashboard.refresh_ui()
    assert _reactive_buttons(dashboard) == []
    assert dashboard._premium_viz is None


def test_o_tich_trong_thiet_lap_luu_va_khoa_o_visualizer(qapp, mock_engine, qtbot):
    from ui.dialogs.settings_dialog import SettingsDialog
    dashboard = _make_dashboard(qtbot, premium=True)

    with patch("core.entitlements.is_premium", return_value=True):
        dlg = SettingsDialog(dashboard)
        qtbot.addWidget(dlg)
        assert dlg._cb_reduce_fx.isChecked() is False
        assert dlg._cb_show_viz.isEnabled() is True

        dlg._cb_reduce_fx.setChecked(True)
        assert dlg._cb_show_viz.isEnabled() is False      # bị ghi đè → khoá ngay
        dlg._cb_reduce_fx.setChecked(False)
        assert dlg._cb_show_viz.isEnabled() is True
        dlg._cb_reduce_fx.setChecked(True)

        with patch("frontend_qt.backend.ConfigManager.save_settings") as save, \
             patch.object(dashboard, "_apply_effects_setting") as apply_fx, \
             patch.object(dashboard, "_apply_visualizer_setting") as apply_viz:
            dlg._save()

    assert save.call_args.args[0]["reduce_effects"] is True
    apply_fx.assert_called_once()
    apply_viz.assert_called_once()
