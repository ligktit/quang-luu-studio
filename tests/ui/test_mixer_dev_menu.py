"""Menu chuột phải Dev Mode trên MIXER phải nhắm đúng kênh được bấm."""
import copy
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMenu

from core.config import UiConfigManager
from ui.panels.mixer import build_panel_mixer


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


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
    layout["mixer"][3]["hidden"] = True  # Giọng đã ẩn
    with patch("ui.panels.mixer.backend.UiConfigManager.load_ui_config", return_value=layout):
        panel = build_panel_mixer(dash)
    qtbot.addWidget(panel)
    _click_menu(dash._mixer_channels["mix_reverb"], "Sửa")
    assert dash._on_edit_widget.call_args.args[1]["id"] == "mix_reverb"
