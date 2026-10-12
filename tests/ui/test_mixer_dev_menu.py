"""Menu chuột phải Dev Mode trên MIXER phải nhắm đúng kênh được bấm."""
import copy
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QDialog, QMenu

from core.config import UiConfigManager
from frontend_qt import MainDashboard, _find_widget_index
from ui.panels.mixer import build_panel_mixer


def _dashboard():
    dash = MagicMock()
    dash.settings = {}
    dash.is_dev_mode = True
    dash.MIDI_CC = {"mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "voice_fx": 54}
    return dash


def _click_menu(view, text):
    """Mở menu chuột phải của kênh và bấm mục `text`."""
    class FakeMenu(QMenu):
        # Không mở menu thật (modal) — bấm thẳng mục cần thử.
        def exec(self, *_a, **_k):
            next(a for a in self.actions() if a.text() == text).trigger()
    # show_ctx import QMenu lúc chạy → đổi thuộc tính của module là đủ.
    with patch("PySide6.QtWidgets.QMenu", FakeMenu):
        view.customContextMenuRequested.emit(QPoint(1, 1))


@pytest.mark.parametrize("cc, wid", [("mix_music", "mix_music"), ("mix_mic", "mix_mic")])
def test_an_kenh_nham_dung_kenh_duoc_bam(qapp, qtbot, cc, wid):
    dash = _dashboard()
    layout = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    with patch("ui.panels.mixer.backend.UiConfigManager.load_ui_config", return_value=layout):
        panel = build_panel_mixer(dash)
    qtbot.addWidget(panel)
    _click_menu(dash._mixer_channels[cc], "Ẩn")
    panel_name, cfg = dash._on_hide_widget.call_args.args
    assert (panel_name, cfg["id"]) == ("mixer", wid)


def test_sau_khi_an_giong_van_sua_duoc_kenh_khac(qapp, qtbot):
    dash = _dashboard()
    layout = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    next(e for e in layout["mixer"] if e["id"] == "voice_fx")["hidden"] = True  # Giọng đã ẩn
    with patch("ui.panels.mixer.backend.UiConfigManager.load_ui_config", return_value=layout):
        panel = build_panel_mixer(dash)
    qtbot.addWidget(panel)
    _click_menu(dash._mixer_channels["mix_reverb"], "Sửa")
    assert dash._on_edit_widget.call_args.args[1]["id"] == "mix_reverb"


@pytest.mark.parametrize("action, handler", [("Sửa", "_on_edit_widget"), ("Ẩn", "_on_hide_widget")])
def test_menu_kenh_giong_nham_giong(qapp, qtbot, action, handler):
    dash = _dashboard()
    layout = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    with patch("ui.panels.mixer.backend.UiConfigManager.load_ui_config", return_value=layout):
        panel = build_panel_mixer(dash)
    qtbot.addWidget(panel)
    _click_menu(dash._mixer_channels["voice_fx"], action)
    assert getattr(dash, handler).call_args.args[1]["id"] == "voice_fx"


def test_tim_entry_thieu_id_khop_theo_noi_dung():
    a = {"cc": "mix_music", "label": "A"}
    b = {"cc": "mix_mic", "label": "B"}
    panel_list = [a, dict(b)]
    # So theo id thì None == None trúng entry đầu — phải ra đúng entry thứ hai.
    assert _find_widget_index(panel_list, b) == 1
    assert _find_widget_index([{"id": "x"}, {"id": "y"}], {"id": "y"}) == 1
    assert _find_widget_index([a], {"cc": "mix_reverb"}) is None


def test_an_entry_khong_con_thi_bao_loi_khong_luu():
    dash = MagicMock()
    with patch("frontend_qt.backend.UiConfigManager.load_ui_config",
               return_value={"mixer": [{"id": "mix_music"}]}), \
         patch("frontend_qt.backend.UiConfigManager.save_ui_config") as save:
        MainDashboard._on_hide_widget(dash, "mixer", {"id": "tone_music"})
    save.assert_not_called()
    assert dash._show_message.call_args.kwargs["is_error"] is True


def test_sua_entry_khong_con_thi_khong_luu_khong_calibration():
    dash = MagicMock()
    dash._builder_context.return_value = {}
    with patch("ui.dialogs.widget_builder.WidgetBuilderDialog") as Dlg, \
         patch("frontend_qt.backend.UiConfigManager.load_ui_config",
               return_value={"mixer": [{"id": "mix_music"}]}), \
         patch("frontend_qt.backend.UiConfigManager.save_ui_config") as save:
        Dlg.return_value.exec.return_value = QDialog.Accepted
        Dlg.return_value.result_data = {"id": "tone_music", "label": "X"}
        Dlg.return_value.result_calibration = {"toggle_invert": {"be": True}}
        MainDashboard._on_edit_widget(dash, "mixer", {"id": "tone_music"})
    save.assert_not_called()
    dash._apply_widget_calibration.assert_not_called()
    assert dash._show_message.call_args.kwargs["is_error"] is True


def test_hai_kenh_trung_cc_chi_dung_kenh_dau(qapp, qtbot):
    dash = _dashboard()
    layout = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    layout["mixer"].append({"id": "custom_dup", "type": "slider", "label": "Nhạc 2",
                            "cc": "mix_music", "range": [0, 100]})
    with patch("ui.panels.mixer.backend.UiConfigManager.load_ui_config", return_value=layout):
        panel = build_panel_mixer(dash)
    qtbot.addWidget(panel)
    assert dash._mixer_channels["mix_music"].slider is dash._mixer_sliders["mix_music"]
    _click_menu(dash._mixer_channels["mix_music"], "Ẩn")
    assert dash._on_hide_widget.call_args.args[1]["id"] == "mix_music"


def test_slider_custom_khong_gan_cc_khong_chiem_kenh_nhac(qapp, qtbot):
    dash = _dashboard()
    layout = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    layout["mixer"].append({"id": "custom_nocc", "type": "slider", "label": "Trống",
                            "range": [0, 100]})
    with patch("ui.panels.mixer.backend.UiConfigManager.load_ui_config", return_value=layout):
        panel = build_panel_mixer(dash)
    qtbot.addWidget(panel)
    assert "custom_nocc" in dash._mixer_channels
    assert dash._mixer_channels["mix_music"] is not dash._mixer_channels["custom_nocc"]
    dash.engine.send_midi.reset_mock()
    dash.engine.set_browser_volume.reset_mock()
    dash._mixer_sliders["custom_nocc"].setValue(50)
    dash.engine.send_midi.assert_not_called()
    dash.engine.set_browser_volume.assert_not_called()
