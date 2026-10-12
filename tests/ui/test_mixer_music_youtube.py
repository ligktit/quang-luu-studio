"""Thanh Nhạc chỉ điều khiển player YouTube, không gửi CC sang DAW (Studio One
lẫn Cubase); không có player thì kênh bị khoá và xám."""
import copy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.config import UiConfigManager
from frontend_qt import MainDashboard
from ui.components.hmixer_channel import HMixerChannel
from ui.panels.mixer import build_panel_mixer


def _build(qtbot):
    dash = MagicMock()
    dash.settings = {}
    dash.is_dev_mode = False
    dash.MIDI_CC = {"mix_music": 20, "mute_music": 50, "mix_mic": 21, "mix_reverb": 22, "voice_fx": 54}
    layout = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    with patch("ui.panels.mixer.backend.UiConfigManager.load_ui_config", return_value=layout):
        panel = build_panel_mixer(dash)
    qtbot.addWidget(panel)
    dash.engine.reset_mock()
    dash.panel = panel   # giữ tham chiếu — panel bị thu gom thì slider con cũng mất
    return dash


def test_keo_thanh_nhac_chi_chinh_youtube(qapp, qtbot):
    dash = _build(qtbot)
    dash._mixer_sliders["mix_music"].setValue(40)
    dash.engine.set_browser_volume.assert_called_with(40)
    dash.engine.send_midi.assert_not_called()


def test_dong_bo_mixer_khong_gui_cc_nhac(qapp, qtbot):
    dash = _build(qtbot)
    dash._mixer_senders["mix_music"](55)
    dash.engine.set_browser_volume.assert_called_with(55)
    dash.engine.send_midi.assert_not_called()


def test_mute_nhac_chi_tat_youtube(qapp, qtbot):
    dash = _build(qtbot)
    ch = dash._mixer_channels["mix_music"]
    ch.slider.setValue(65)
    dash.engine.reset_mock()

    ch.mute_btn.click()
    dash.engine.set_browser_volume.assert_called_with(0)
    ch.mute_btn.click()
    dash.engine.set_browser_volume.assert_called_with(65)
    dash.engine.send_midi.assert_not_called()


def test_kenh_khong_kha_dung_bi_khoa_va_mo_lai_dung_trang_thai(qapp, qtbot):
    ch = HMixerChannel(icon="♪", label="Nhạc", color="#14b8a6", cc_key="mix_music")
    qtbot.addWidget(ch)

    ch.set_available(False, "chưa có YouTube")
    assert not ch.slider.isEnabled() and not ch.mute_btn.isEnabled()
    assert ch.toolTip() == "chưa có YouTube"

    ch.set_available(True)
    assert ch.slider.isEnabled() and ch.mute_btn.isEnabled()
    assert ch.toolTip() == ""

    # Đang mute mà mất player rồi có lại: vẫn mute, thanh vẫn khoá, nút mute dùng được.
    ch.toggle_mute()
    ch.set_available(False, "x")
    ch.set_available(True)
    assert ch.is_muted()
    assert not ch.slider.isEnabled() and ch.mute_btn.isEnabled()
    assert ch.val_label.text() == "MUTED"


def _stub_dashboard(qtbot, available):
    ch = HMixerChannel(icon="♪", label="Nhạc", color="#14b8a6", cc_key="mix_music", default=70)
    qtbot.addWidget(ch)
    engine = MagicMock()
    engine.browser_volume_available.return_value = available
    return SimpleNamespace(
        _mixer_channels={"mix_music": ch}, engine=engine, mute_states={},
        _MUSIC_UNAVAILABLE_TIP=MainDashboard._MUSIC_UNAVAILABLE_TIP,
    ), ch


def test_khong_co_player_thi_xam_thanh_nhac(qapp, qtbot):
    dash, ch = _stub_dashboard(qtbot, available=False)
    MainDashboard._update_music_channel_availability(dash)
    assert not ch.is_available() and not ch.slider.isEnabled()
    dash.engine.set_browser_volume.assert_not_called()


def test_co_player_tro_lai_thi_day_muc_dang_hien(qapp, qtbot):
    dash, ch = _stub_dashboard(qtbot, available=False)
    MainDashboard._update_music_channel_availability(dash)
    ch.slider.setValue(35)          # đổi lúc đang xám (preset / mức theo bài)

    dash.engine.browser_volume_available.return_value = True
    MainDashboard._update_music_channel_availability(dash)
    assert ch.is_available()
    dash.engine.set_browser_volume.assert_called_once_with(35)

    # Nhịp kiểm tra sau không đẩy lại khi trạng thái không đổi.
    MainDashboard._update_music_channel_availability(dash)
    dash.engine.set_browser_volume.assert_called_once()


def test_co_player_tro_lai_khi_dang_mute_thi_day_0(qapp, qtbot):
    dash, ch = _stub_dashboard(qtbot, available=False)
    MainDashboard._update_music_channel_availability(dash)
    dash.mute_states["mix_music"] = True
    dash.engine.browser_volume_available.return_value = True
    MainDashboard._update_music_channel_availability(dash)
    dash.engine.set_browser_volume.assert_called_once_with(0)
