"""Hai micro trên Studio One — kênh Mic 2 trên mixer (spec 6.4).

Kênh Mic 2 là phần mở rộng CHỈ có khi `mic_count == 2`: cùng số CC với Mic
nhưng gửi trên kênh MIDI 2 (index 1). Máy một mic không được thấy gì khác.
"""
import copy
from unittest.mock import MagicMock, call, patch

import pytest

pytest.importorskip("PySide6.QtWidgets")

from frontend_qt import MainDashboard


@pytest.fixture
def engine_cls():
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = "http://yt.com"
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._youtube_watcher_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        yield mock_eng


@pytest.fixture
def mock_engine(engine_cls):
    return engine_cls.return_value


@pytest.fixture
def save_settings():
    # Bấm tắt/mở mic khi bật 2 mic ghi settings.json ngay — test không được
    # đụng file thật.
    with patch("frontend_qt.backend.ConfigManager.save_settings") as save:
        yield save


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


def _channel_calls(engine):
    return [c.args[:3] for c in engine.send_midi_on_channel.call_args_list]


def test_dashboard_va_engine_dung_chung_mot_dict_settings(qapp, engine_cls, qtbot):
    # MainDashboard() không truyền settings: trước đây engine nhận None còn
    # dashboard tự tạo {} → hai dict lệch nhau, refresh_mic2_mirror đọc nhầm.
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        dash = MainDashboard()
        qtbot.addWidget(dash)
        if dash._so_ready_watcher is not None:
            dash._so_ready_watcher.stop()
    assert engine_cls.call_args.args[0] is dash.settings


def test_single_mic_unchanged(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot)
    assert "mix_mic_2" not in dash._mixer_sliders
    assert "mix_mic_2" not in dash.mute_states
    assert dash._mixer_channels["mix_mic"]._name_text == "Mic"

    mock_engine.reset_mock()
    dash._mixer_sliders["mix_mic"].setValue(3)
    assert [c.args[0] for c in mock_engine.send_midi.call_args_list] == [21]
    mock_engine.send_midi_on_channel.assert_not_called()

    dash._mixer_channels["mix_mic"].mute_btn.click()
    mock_engine.send_midi.assert_any_call(51, 127)
    mock_engine.send_midi_on_channel.assert_not_called()
    save_settings.assert_not_called()
    assert "mic_mutes" not in dash.settings


def test_mic2_strip_sends_channel_2(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 2, "mixer_levels": {"mix_mic_2": 3},
                                   "mic_mutes": {"mix_mic": False, "mix_mic_2": False}})
    keys = list(dash._mixer_channels)
    assert keys[keys.index("mix_mic") + 1] == "mix_mic_2"
    assert dash._mixer_channels["mix_mic"]._name_text == "Mic Dây"
    assert dash._mixer_channels["mix_mic_2"]._name_text == "Mic Không Dây"
    assert dash._mixer_sliders["mix_mic_2"].value() == 3

    mock_engine.reset_mock()
    dash._mixer_sliders["mix_mic_2"].setValue(0)
    mock_engine.send_midi_on_channel.assert_called_once_with(1, 21, 76)
    mock_engine.send_midi.assert_not_called()

    mock_engine.reset_mock()
    dash._mixer_channels["mix_mic_2"].mute_btn.click()
    assert (1, 51, 127) in _channel_calls(mock_engine)
    mock_engine.send_midi.assert_not_called()
    assert dash.mute_states["mix_mic_2"] is True
    assert dash.mute_states["mix_mic"] is False


def test_mic2_nhan_tu_cai_dat(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 2,
                                   "mic_labels": {"mix_mic": "Mic A", "mix_mic_2": "Mic B"}})
    assert dash._mixer_channels["mix_mic"]._name_text == "Mic A"
    assert dash._mixer_channels["mix_mic_2"]._name_text == "Mic B"


def test_mic2_mute_gui_ca_cc_phu_cua_mic_tren_kenh_2(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 2, "mic_mutes": {"mix_mic": False, "mix_mic_2": False}})
    multi = {"mix_mic": [{"cc": 60, "on_value": 127, "off_value": 0}]}
    mock_engine.reset_mock()
    with patch("frontend_qt.backend.AppConfig.get_mute_multi_cc", return_value=multi):
        dash._mixer_channels["mix_mic_2"].mute_btn.click()
    assert _channel_calls(mock_engine) == [(1, 51, 127), (1, 60, 127)]
    mock_engine.send_midi.assert_not_called()


def test_mic_mutes_persist_and_resync(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 2, "mic_mutes": {"mix_mic": False, "mix_mic_2": False}})
    dash._mixer_channels["mix_mic_2"].mute_btn.click()
    assert dash.settings["mic_mutes"]["mix_mic_2"] is True
    assert dash.settings["mic_mutes"]["mix_mic"] is False
    save_settings.assert_called_with(dash.settings)

    dash2 = _make_dashboard(qtbot, copy.deepcopy(dash.settings))
    assert dash2.mute_states["mix_mic_2"] is True
    assert dash2.mute_states["mix_mic"] is False
    assert dash2._mixer_channels["mix_mic_2"].is_muted() is True
    assert dash2._mixer_channels["mix_mic"].is_muted() is False

    mock_engine.reset_mock()
    dash2._sync_midi_states()
    assert (1, 51, 127) in _channel_calls(mock_engine)
    mock_engine.send_midi.assert_any_call(51, 0)
    # Mức Mic 2 cũng được bắn lại trên kênh 2.
    assert any(c[:2] == (1, 21) for c in _channel_calls(mock_engine))


def test_mic_mutes_chi_doc_khi_bat_2_mic(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 1,
                                   "mic_mutes": {"mix_mic": True, "mix_mic_2": True}})
    assert dash.mute_states["mix_mic"] is False
    assert "mix_mic_2" not in dash.mute_states
    assert dash._mixer_channels["mix_mic"].is_muted() is False


def test_toggle_mic_count_rebuilds_and_rewires(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot)
    dash._mixer_sliders["mix_mic"].setValue(5)
    mock_engine.reset_mock()

    dash.settings["mic_count"] = 2
    dash._apply_mic_count_setting()
    assert "mix_mic_2" in dash._mixer_sliders
    mock_engine.refresh_mic2_mirror.assert_called()
    # Mức đang chỉnh không bị nhảy về giá trị cũ khi dựng lại mixer.
    assert dash._mixer_sliders["mix_mic"].value() == 5
    # Lần đầu bật (chưa có mic_mutes): Mic 2 tắt sẵn, Mic 1 vẫn mở; lượt
    # đồng bộ sau khi đổi đã bắn mute Mic 2 sang kênh 2.
    assert dash.mute_states["mix_mic_2"] is True
    assert dash._mixer_channels["mix_mic_2"].is_muted() is True
    assert dash.mute_states["mix_mic"] is False
    assert (1, 51, 127) in _channel_calls(mock_engine)

    mock_engine.reset_mock()
    dash._mixer_sliders["mix_mic_2"].setValue(-10)
    mock_engine.send_midi_on_channel.assert_called_once_with(1, 21, 0)

    mock_engine.reset_mock()
    dash.settings["mic_count"] = 1
    dash._apply_mic_count_setting()
    assert "mix_mic_2" not in dash._mixer_sliders
    assert "mix_mic_2" not in dash._mixer_channels
    mock_engine.refresh_mic2_mirror.assert_called()
    mock_engine.send_midi_on_channel.assert_not_called()
    assert dash._mixer_channels["mix_mic"]._name_text == "Mic"


def test_toggle_mic_count_giu_trang_thai_tat_mic(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 2})
    dash._mixer_channels["mix_mic"].mute_btn.click()
    dash.settings["mic_labels"] = {"mix_mic": "Dây", "mix_mic_2": "Không dây"}
    dash._apply_mic_count_setting()
    assert dash._mixer_channels["mix_mic"].is_muted() is True
    assert dash._mixer_channels["mix_mic"]._name_text == "Dây"
    assert dash._mixer_channels["mix_mic_2"]._name_text == "Không dây"


# ── Cài đặt → Âm thanh → Micro ──
A11Y_CFG = {
    "tts_enabled": False, "tts_engine": "sapi", "tts_voice": "", "tts_rate": 170,
    "voice_command_enabled": False, "voice_model": "small",
    "high_contrast": False, "focus_ring_thick": False, "font_scale": 1.0,
    "announce_focus": True, "announce_state": True,
}


def _open_dialog(qtbot, dashboard):
    from ui.dialogs.settings_dialog import SettingsDialog
    with patch("frontend_qt.backend.AppConfig.get_accessibility", return_value=dict(A11Y_CFG)):
        dlg = SettingsDialog(dashboard)
    qtbot.addWidget(dlg)
    return dlg


def _save(dlg):
    d = dlg._dashboard
    with patch("frontend_qt.backend.ConfigManager.save_settings"), \
         patch("frontend_qt.backend.AppConfig.update"), \
         patch("frontend_qt.backend.AppConfig.save"), \
         patch("frontend_qt.backend.AppConfig.set_accessibility"), \
         patch.object(d, "_apply_embedded_player_setting"), \
         patch.object(d, "_apply_visualizer_setting"), \
         patch.object(d, "_apply_auto_echo_setting"), \
         patch.object(d, "_apply_auto_noise_setting"), \
         patch.object(d, "_apply_mic_count_setting") as apply_mic:
        dlg._save()
    return apply_mic


def test_cai_dat_bat_2_mic_ghi_khoa_va_dung_lai_mixer(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    dlg = _open_dialog(qtbot, dash)
    assert dlg._cb_two_mics.isChecked() is False
    assert not dlg._inp_mic_label_1.isEnabled() and not dlg._inp_mic_label_2.isEnabled()

    dlg._cb_two_mics.setChecked(True)
    assert dlg._inp_mic_label_1.isEnabled() and dlg._inp_mic_label_2.isEnabled()
    assert dlg._inp_mic_label_1.text() == "Mic Dây"
    assert dlg._inp_mic_label_2.text() == "Mic Không Dây"
    dlg._inp_mic_label_2.setText("Mic KG")
    apply_mic = _save(dlg)

    assert dash.settings["mic_count"] == 2
    assert dash.settings["mic_labels"] == {"mix_mic": "Mic Dây", "mix_mic_2": "Mic KG"}
    apply_mic.assert_called_once()


def test_cai_dat_khong_doi_gi_thi_khong_dung_lai_mixer(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    dlg = _open_dialog(qtbot, dash)
    apply_mic = _save(dlg)
    apply_mic.assert_not_called()


def test_cai_dat_doi_nhan_thi_dung_lai_mixer(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 2})
    dlg = _open_dialog(qtbot, dash)
    assert dlg._cb_two_mics.isChecked() is True
    dlg._inp_mic_label_1.setText("Mic Shure")
    apply_mic = _save(dlg)
    assert dash.settings["mic_labels"]["mix_mic"] == "Mic Shure"
    apply_mic.assert_called_once()


def test_cai_dat_cubase_vo_hieu_o_2_mic(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    dlg = _open_dialog(qtbot, dash)
    assert dlg._cb_two_mics.isEnabled() is True
    dlg._cmb_daw.setCurrentIndex(dlg._cmb_daw.findData("cubase"))
    assert dlg._cb_two_mics.isEnabled() is False
    assert dlg._cb_two_mics.toolTip() == "Chỉ hỗ trợ Studio One"
    dlg._cmb_daw.setCurrentIndex(dlg._cmb_daw.findData("studio_one"))
    assert dlg._cb_two_mics.isEnabled() is True


def test_cai_dat_cubase_khong_ghi_de_mic_count(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 2})
    dlg = _open_dialog(qtbot, dash)
    dlg._cmb_daw.setCurrentIndex(dlg._cmb_daw.findData("cubase"))
    apply_mic = _save(dlg)
    assert dash.settings["mic_count"] == 2
    # Chuyển sang Cubase làm tắt hai mic → phải dựng lại mixer / tắt phát đôi.
    apply_mic.assert_called_once()


def test_cai_dat_cubase_ve_studio_one_giu_o_2_mic(qapp, mock_engine, qtbot):
    # Máy đang Cubase mà vẫn lưu mic_count=2: ô hiện tick (bị khoá); chuyển về
    # Studio One rồi lưu thì không được ghi mất số 2.
    dash = _make_dashboard(qtbot, {"mic_count": 2, "daw_kind": "cubase"})
    dlg = _open_dialog(qtbot, dash)
    assert dlg._cb_two_mics.isChecked() is True and dlg._cb_two_mics.isEnabled() is False
    dlg._cmb_daw.setCurrentIndex(dlg._cmb_daw.findData("studio_one"))
    apply_mic = _save(dlg)
    assert dash.settings["mic_count"] == 2
    apply_mic.assert_called_once()


def test_hai_mic_noi_cot_ten_cho_vua_mic_khong_day(qapp, mock_engine, save_settings, qtbot):
    # "Mic Không Dây" dài hơn cột tên 52px mặc định → nới cột tên mọi kênh
    # (thẳng hàng), chỉ trên máy hai mic.
    one = _make_dashboard(qtbot)
    assert {ch._name_lbl.minimumWidth() for ch in one._mixer_channels.values()} == {52}

    dash = _make_dashboard(qtbot, {"mic_count": 2})
    lbl = dash._mixer_channels["mix_mic_2"]._name_lbl
    widths = {ch._name_lbl.minimumWidth() for ch in dash._mixer_channels.values()}
    assert len(widths) == 1
    assert widths.pop() >= lbl.fontMetrics().horizontalAdvance("Mic Không Dây")


def test_lan_dau_bat_2_mic_mic2_tat_san(qapp, mock_engine, save_settings, qtbot):
    # Spec 5.3: mic không dây không dùng không được để mở.
    dash = _make_dashboard(qtbot, {"mic_count": 2})
    assert dash.mute_states["mix_mic_2"] is True
    assert dash.mute_states["mix_mic"] is False
    assert dash._mixer_channels["mix_mic_2"].is_muted() is True
    mock_engine.reset_mock()
    dash._sync_midi_states()
    assert (1, 51, 127) in _channel_calls(mock_engine)


def test_cubase_khong_co_mic2(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 2, "daw_kind": "cubase"})
    assert "mix_mic_2" not in dash._mixer_channels
    assert "mix_mic_2" not in dash.mute_states
    mock_engine.reset_mock()
    dash._sync_midi_states()
    mock_engine.send_midi_on_channel.assert_not_called()


def test_dung_lai_mixer_giu_hinh_tat_moi_kenh(qapp, mock_engine, save_settings, qtbot):
    # Trước đây dựng lại mixer thì Vang hiện "mở" trong khi DAW vẫn đang tắt.
    dash = _make_dashboard(qtbot)
    dash._mixer_channels["mix_reverb"].mute_btn.click()
    dash.settings["mic_count"] = 2
    dash._apply_mic_count_setting()
    assert dash._mixer_channels["mix_reverb"].is_muted() is True
    assert dash._mixer_channels["mix_mic"].is_muted() is False


def test_tat_mic_gui_midi_truoc_roi_moi_ghi_dia(qapp, mock_engine, save_settings, qtbot):
    dash = _make_dashboard(qtbot, {"mic_count": 2})
    order = []
    mock_engine.send_midi.side_effect = lambda *a, **k: order.append("midi")
    mock_engine.send_midi_on_channel.side_effect = lambda *a, **k: order.append("midi")
    save_settings.side_effect = lambda *a, **k: order.append("save")
    for key in ("mix_mic", "mix_mic_2"):
        order.clear()
        dash._mixer_channels[key].mute_btn.click()
        # Mọi lệnh MIDI của lần bấm đi trước, ghi đĩa sau cùng.
        assert order[0] == "midi" and order[-1] == "save" and order.count("save") == 1
