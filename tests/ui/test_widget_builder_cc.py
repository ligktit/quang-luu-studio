"""Widget Builder: cảnh báo CC trùng và nút Gửi thử."""
import copy
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication

from core.config import DEFAULT_MODE_CONFIG, DEFAULT_TOGGLE_INVERT, UiConfigManager
from ui.dialogs.widget_builder import WidgetBuilderDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def cfg():
    modes = {k: dict(v) for k, v in DEFAULT_MODE_CONFIG.items()}
    invert = dict(DEFAULT_TOGGLE_INVERT)
    with patch("core.config.AppConfig.get_mode_config", return_value=modes), \
         patch("core.config.AppConfig.get_toggle_invert", return_value=invert):
        yield modes, invert


@pytest.fixture
def layout():
    ui = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    ui["tools"].append({"id": "custom_1", "type": "button", "label": "Vang HT", "cc": 60})
    return ui


def _dlg(qtbot, **kw):
    kw.setdefault("panel_name", "tools")
    kw.setdefault("widget_type", "button")
    kw.setdefault("midi_cc", {"mix_music": 20})
    dlg = WidgetBuilderDialog(None, **kw)
    qtbot.addWidget(dlg)
    dlg.label_input.setText("Nút thử")
    return dlg


def test_canh_bao_cc_trung_khong_chan_luu(qapp, qtbot, cfg, layout):
    dlg = _dlg(qtbot, ui_config=layout)
    assert dlg.cc_note.text() == ""
    dlg.cc_input.setValue(60)
    assert "Vang HT (Tools)" in dlg.cc_note.text()
    assert dlg.save_btn.isEnabled()
    dlg.cc_input.setValue(20)
    assert "Nhạc (Mixer)" in dlg.cc_note.text()
    dlg.cc_input.setValue(99)
    assert dlg.cc_note.text() == ""


def test_sua_chinh_no_khong_tu_canh_bao(qapp, qtbot, cfg, layout):
    dlg = _dlg(qtbot, ui_config=layout, existing_data=dict(layout["tools"][-1]))
    assert dlg.cc_input.value() == 60
    assert dlg.cc_note.text() == ""


def test_nhan_cc_luon_hien_chieu_cao_co_dinh(qapp, qtbot, cfg, layout):
    dlg = _dlg(qtbot, ui_config=layout)
    h = dlg.cc_note.minimumHeight()
    assert h > 0 and not dlg.cc_note.isHidden()
    dlg.cc_input.setValue(60)
    assert dlg.cc_note.minimumHeight() == h and not dlg.cc_note.isHidden()


def test_gui_thu_gui_bat_roi_tat(qapp, qtbot, cfg, layout):
    engine = MagicMock()
    dlg = _dlg(qtbot, ui_config=layout, engine=engine)
    assert not dlg.test_btn.isEnabled()  # CC chưa gán
    dlg.cc_input.setValue(61)
    assert dlg.test_btn.isEnabled()
    dlg.test_btn.click()
    assert engine.send_midi.call_args_list[0].args == (61, 127)
    qtbot.waitUntil(lambda: engine.send_midi.call_count == 2, timeout=2000)
    assert engine.send_midi.call_args_list[1].args == (61, 0)
    assert "61" in dlg.test_status.text()


def test_gui_thu_thanh_truot(qapp, qtbot, cfg, layout):
    engine = MagicMock()
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider", ui_config=layout, engine=engine)
    dlg.cc_input.setValue(70)
    dlg.test_btn.click()
    qtbot.waitUntil(lambda: engine.send_midi.call_count == 2, timeout=2000)
    assert [c.args for c in engine.send_midi.call_args_list] == [(70, 64), (70, 0)]


def test_gui_thu_khong_co_engine_thi_khoa(qapp, qtbot, cfg, layout):
    dlg = _dlg(qtbot, ui_config=layout)
    dlg.cc_input.setValue(61)
    assert not dlg.test_btn.isEnabled()


def test_gui_thu_loi_khong_crash(qapp, qtbot, cfg, layout):
    engine = MagicMock()
    engine.send_midi.side_effect = RuntimeError("cổng MIDI đóng")
    dlg = _dlg(qtbot, ui_config=layout, engine=engine)
    dlg.cc_input.setValue(61)
    dlg.test_btn.click()
    qtbot.wait(500)
    assert "cổng MIDI đóng" in dlg.test_status.text()
    assert engine.send_midi.call_count == 1  # lỗi lần BẬT → không hẹn gửi TẮT
