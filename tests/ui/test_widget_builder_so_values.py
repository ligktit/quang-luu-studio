"""Dev Mode: nhập giá trị theo Studio One, app tự đổi sang MIDI (+ Bypass)."""
import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication

from core.config import DEFAULT_MODE_CONFIG, DEFAULT_TOGGLE_INVERT
from ui.dialogs.widget_builder import WidgetBuilderDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def cfg():
    """AppConfig giả — dialog đọc mode_config / toggle_invert thật từ đây."""
    modes = {k: dict(v) for k, v in DEFAULT_MODE_CONFIG.items()}
    invert = dict(DEFAULT_TOGGLE_INVERT)
    with patch("core.config.AppConfig.get_mode_config", return_value=modes), \
         patch("core.config.AppConfig.get_toggle_invert", return_value=invert):
        yield modes, invert


def _set_type(dlg, t):
    dlg.so_type_combo.setCurrentIndex(dlg.so_type_combo.findData(t))


def test_nut_moi_gan_bypass(qapp, qtbot, cfg):
    dlg = WidgetBuilderDialog(None, panel_name="tools", widget_type="button")
    qtbot.addWidget(dlg)
    dlg.label_input.setText("Delay")
    dlg.cc_input.setValue(60)
    assert dlg.so_type_combo.currentData() == "switch"
    dlg.bypass_cb.setChecked(True)
    dlg._on_save()
    d = dlg.result_data
    assert (d["cc"], d["on_value"], d["off_value"]) == (60, 0, 127)
    assert d["so_value"] == {"type": "switch", "bypass": True}
    assert dlg.result_calibration is None


def test_nut_moi_phan_tram(qapp, qtbot, cfg):
    dlg = WidgetBuilderDialog(None, panel_name="tools", widget_type="button")
    qtbot.addWidget(dlg)
    dlg.cc_input.setValue(61)
    _set_type(dlg, "percent")
    dlg.on_num.setValue(75)
    dlg.off_num.setValue(0)
    assert "MIDI 95" in dlg.on_preview.text()
    dlg._on_save()
    assert (dlg.result_data["on_value"], dlg.result_data["off_value"]) == (95, 0)


def test_nut_moi_danh_sach(qapp, qtbot, cfg):
    dlg = WidgetBuilderDialog(None, panel_name="mode", widget_type="button")
    qtbot.addWidget(dlg)
    dlg.cc_input.setValue(62)
    _set_type(dlg, "list")
    dlg.options_input.setText("Tắt, Nhẹ, Vừa, Mạnh")
    dlg.on_combo.setCurrentIndex(3)
    dlg.off_combo.setCurrentIndex(0)
    dlg._on_save()
    assert (dlg.result_data["on_value"], dlg.result_data["off_value"]) == (127, 0)
    dlg2 = WidgetBuilderDialog(None, panel_name="mode", widget_type="button",
                               existing_data=dlg.result_data)
    qtbot.addWidget(dlg2)
    # Mở lại: hiện đúng giá trị Studio One đã nhập, không phải số MIDI.
    assert dlg2.so_type_combo.currentData() == "list"
    assert dlg2.on_combo.currentText() == "Mạnh"


def test_danh_sach_thieu_muc_khong_cho_luu(qapp, qtbot, cfg):
    dlg = WidgetBuilderDialog(None, panel_name="tools", widget_type="button")
    qtbot.addWidget(dlg)
    dlg.cc_input.setValue(63)
    _set_type(dlg, "list")
    dlg.options_input.setText("Chỉ một mục")
    dlg._on_save()
    assert dlg.result_data is None
    assert dlg.error_label.text()


def test_entry_cu_chi_co_midi_hien_thanh_cong_tac(qapp, qtbot, cfg):
    old = {"id": "c1", "type": "button", "label": "X", "cc": 70, "on_value": 0, "off_value": 127}
    dlg = WidgetBuilderDialog(None, panel_name="tools", widget_type="button", existing_data=old)
    qtbot.addWidget(dlg)
    assert dlg.so_type_combo.currentData() == "switch"
    assert dlg.bypass_cb.isChecked()


def test_mode_co_san_bypass_ghi_vao_mode_config(qapp, qtbot, cfg):
    modes, _ = cfg
    entry = {"id": "mode_lofi", "type": "button", "label": "Lofi", "action": "set_mode_lofi"}
    dlg = WidgetBuilderDialog(None, panel_name="mode", widget_type="button", existing_data=entry)
    qtbot.addWidget(dlg)
    assert dlg._value_target() == "mode_config"
    dlg.bypass_cb.setChecked(True)
    dlg._on_save()
    assert dlg.result_calibration == {
        "mode_config": {"Lofi": {"cc": modes["Lofi"]["cc"], "on_value": 0, "off_value": 127}}}
    # CC của MODE có sẵn không bị ghi đè vào ui_config.
    assert "cc" not in dlg.result_data


def test_mode_co_san_doc_lai_bypass_tu_mode_config(qapp, qtbot, cfg):
    modes, _ = cfg
    modes["Remix"].update(on_value=0, off_value=127)
    entry = {"id": "mode_remix", "type": "button", "label": "Remix", "action": "set_mode_remix"}
    dlg = WidgetBuilderDialog(None, panel_name="mode", widget_type="button", existing_data=entry)
    qtbot.addWidget(dlg)
    assert dlg.bypass_cb.isChecked()


def test_nut_cong_cu_co_san_chi_co_bypass(qapp, qtbot, cfg):
    _, invert = cfg
    invert["be"] = True
    entry = {"id": "btn_be", "type": "button", "label": "Bè", "action": "be"}
    dlg = WidgetBuilderDialog(None, panel_name="tools", widget_type="button", existing_data=entry)
    qtbot.addWidget(dlg)
    assert dlg._value_target() == "toggle_invert"
    assert not dlg.so_type_combo.isEnabled()
    assert dlg.bypass_cb.isChecked()
    dlg.bypass_cb.setChecked(False)
    dlg._on_save()
    assert dlg.result_calibration == {"toggle_invert": {"be": False}}


def test_nut_khong_gui_midi_khong_ghi_gia_tri(qapp, qtbot, cfg):
    entry = {"id": "btn_rescan", "type": "button", "label": "Dò Lại", "action": "force_rescan"}
    dlg = WidgetBuilderDialog(None, panel_name="tools", widget_type="button", existing_data=entry)
    qtbot.addWidget(dlg)
    assert dlg._value_target() is None
    dlg._on_save()
    assert "on_value" not in dlg.result_data
    assert dlg.result_calibration is None
