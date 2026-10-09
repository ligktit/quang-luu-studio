"""Widget Builder: nhãn thân thiện, ô màu, kiểm tra tức thì."""
import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication

from core.config import DEFAULT_MODE_CONFIG, DEFAULT_TOGGLE_INVERT
from ui.design_tokens import C
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


def _dlg(qtbot, **kw):
    dlg = WidgetBuilderDialog(None, **kw)
    qtbot.addWidget(dlg)
    return dlg


def test_combo_loai_hien_chu_tieng_viet(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider")
    texts = [dlg.type_combo.itemText(i) for i in range(dlg.type_combo.count())]
    assert texts == ["Thanh trượt", "Nút"]
    assert dlg.type_combo.currentData() == "slider"
    assert not dlg.type_row.isHidden()


def test_an_combo_loai_khi_sua_va_o_tools_mode(qapp, qtbot, cfg):
    assert _dlg(qtbot, panel_name="tools", widget_type="button").type_row.isHidden()
    assert _dlg(qtbot, panel_name="mode", widget_type="button").type_row.isHidden()
    entry = {"id": "mix_music", "type": "slider", "label": "Nhạc", "cc": "mix_music",
             "range": [0, 100]}
    assert _dlg(qtbot, panel_name="mixer", widget_type="slider",
                existing_data=entry).type_row.isHidden()


def test_icon_chi_hien_voi_thanh_truot(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider")
    assert not dlg.icon_row.isHidden()
    dlg.type_combo.setCurrentIndex(dlg.type_combo.findData("button"))
    assert dlg.icon_row.isHidden()


def test_bam_o_mau_dien_hex_token(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    assert set(dlg.swatches) == {"primary", "creative", "accent", "green",
                                 "orange", "pink", "deep_purple", "blue"}
    dlg.swatches["green"].click()
    assert dlg.color_input.text() == C["green"]


def test_ten_rong_khoa_luu(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    assert not dlg.save_btn.isEnabled()
    assert "tên" in dlg.error_label.text().lower()
    dlg.label_input.setText("Vang HT")
    assert dlg.save_btn.isEnabled()
    assert dlg.error_label.text() == ""


def test_mau_sai_khoa_luu(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    dlg.label_input.setText("X")
    dlg.color_input.setText("#12345")
    assert not dlg.save_btn.isEnabled()
    assert "màu" in dlg.error_label.text().lower()
    dlg.color_input.setText("")  # để trống = màu mặc định, hợp lệ
    assert dlg.save_btn.isEnabled()


def test_min_lon_hon_max_khoa_luu(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider")
    dlg.label_input.setText("Kênh")
    dlg.min_val.setValue(50)
    dlg.max_val.setValue(10)
    assert not dlg.save_btn.isEnabled()
    assert "min" in dlg.error_label.text().lower()
    dlg._on_save()
    assert dlg.result_data is None


def test_khoang_so_trung_khoa_luu(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    dlg.label_input.setText("X")
    dlg.cc_input.setValue(60)
    dlg.so_type_combo.setCurrentIndex(dlg.so_type_combo.findData("range"))
    dlg.range_min.setValue(5)
    dlg.range_max.setValue(5)
    assert not dlg.save_btn.isEnabled()


def test_luu_ghi_type_theo_data(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider")
    dlg.label_input.setText("Kênh")
    dlg._on_save()
    assert dlg.result_data["type"] == "slider"


def test_nhan_loi_luon_hien_chieu_cao_co_dinh(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    h = dlg.error_label.minimumHeight()
    assert h > 0 and not dlg.error_label.isHidden()
    dlg.label_input.setText("X")
    assert not dlg.error_label.isHidden()
    assert dlg.error_label.minimumHeight() == h
