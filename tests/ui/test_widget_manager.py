"""Hộp Quản lý giao diện (Dev Mode)."""
import copy
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from core.config import UiConfigManager
from ui.dialogs.widget_manager import WidgetManagerDialog

YES = QMessageBox.Yes
NO = QMessageBox.No


@pytest.fixture
def layout():
    ui = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    ui["tools"].append({"id": "custom_1", "type": "button", "label": "Vang HT", "cc": 60})
    return ui


def _dlg(qtbot, layout, panel="tools"):
    dlg = WidgetManagerDialog(None, panel_name=panel, ui_config=layout, midi_cc={})
    qtbot.addWidget(dlg)
    return dlg


def _ids(dlg, panel):
    lst = dlg.lists[panel]
    return [lst.item(i).data(Qt.UserRole) for i in range(lst.count())]


def test_mo_dung_tab_va_khong_dong_vao_ban_goc(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout, "mode")
    assert dlg.current_panel() == "mode"
    assert _ids(dlg, "tools")[-1] == "custom_1"
    dlg.select("tools", "btn_rescan")
    dlg.down_btn.click()
    assert layout["tools"][1]["id"] == "btn_rescan"  # bản gốc không đổi


def test_len_xuong_doi_thu_tu(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "custom_1")
    dlg.up_btn.click()
    assert _ids(dlg, "tools")[-2] == "custom_1"
    assert [e["id"] for e in dlg.working["tools"]][-2] == "custom_1"
    assert dlg.lists["tools"].currentItem().data(Qt.UserRole) == "custom_1"


def test_keo_tha_dong_bo_thu_tu(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    lst = dlg.lists["tools"]
    item = lst.takeItem(lst.count() - 1)
    lst.insertItem(0, item)
    dlg._sync_order("tools")
    assert dlg.working["tools"][0]["id"] == "custom_1"


def test_bo_tick_la_an(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    item = dlg.lists["tools"].item(1)
    item.setCheckState(Qt.Unchecked)
    assert dlg.working["tools"][1]["hidden"] is True
    item.setCheckState(Qt.Checked)
    assert dlg.working["tools"][1]["hidden"] is False


def test_widget_an_hien_bo_tick(qapp, qtbot, layout):
    layout["mixer"][2]["hidden"] = True
    dlg = _dlg(qtbot, layout, "mixer")
    assert dlg.lists["mixer"].item(2).checkState() == Qt.Unchecked


def test_xoa_chi_cho_widget_tu_them(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "btn_rescan")
    assert not dlg.delete_btn.isEnabled()
    dlg.select("tools", "custom_1")
    assert dlg.delete_btn.isEnabled()
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=YES):
        dlg.delete_btn.click()
    assert "custom_1" not in _ids(dlg, "tools")


def test_xoa_hoi_khong_thi_giu(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "custom_1")
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=NO):
        dlg.delete_btn.click()
    assert "custom_1" in _ids(dlg, "tools")


def test_khoi_phuc_mac_dinh_panel(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=YES):
        dlg.reset_btn.click()
    assert "custom_1" not in _ids(dlg, "tools")
    assert len(_ids(dlg, "tools")) == len(UiConfigManager._DEFAULT_UI_CONFIG["tools"])


def _fake_builder(result, calibration=None):
    inst = MagicMock()
    inst.exec.return_value = QDialog.Accepted
    inst.result_data = result
    inst.result_calibration = calibration
    return MagicMock(return_value=inst)


def test_sua_ghi_vao_ban_sao_va_gom_calibration(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "btn_be")
    new = dict(dlg.working["tools"][4], label="Bè 2")
    fake = _fake_builder(new, {"toggle_invert": {"be": True}})
    with patch("ui.dialogs.widget_manager.WidgetBuilderDialog", fake):
        dlg.edit_btn.click()
    kwargs = fake.call_args.kwargs
    assert kwargs["existing_data"]["id"] == "btn_be"
    assert kwargs["ui_config"] is dlg.working
    assert dlg.working["tools"][4]["label"] == "Bè 2"
    assert dlg.calibrations == [{"toggle_invert": {"be": True}}]


def test_them_noi_cuoi_va_chon(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout, "mixer")
    fake = _fake_builder({"id": "custom_9", "type": "slider", "label": "Kênh", "cc": 70})
    with patch("ui.dialogs.widget_manager.WidgetBuilderDialog", fake):
        dlg.add_btn.click()
    assert fake.call_args.kwargs["widget_type"] == "slider"
    assert _ids(dlg, "mixer")[-1] == "custom_9"
    assert dlg.lists["mixer"].currentItem().data(Qt.UserRole) == "custom_9"


def test_luu_ghi_file_va_accept(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "custom_1")
    dlg.up_btn.click()
    with patch("ui.dialogs.widget_manager.UiConfigManager.save_ui_config",
               return_value=True) as save:
        dlg.save_btn.click()
    save.assert_called_once()
    assert [e["id"] for e in save.call_args.args[0]["tools"]][-2] == "custom_1"
    assert dlg.result() == QDialog.Accepted


def test_luu_loi_thi_o_lai(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    with patch("ui.dialogs.widget_manager.UiConfigManager.save_ui_config", return_value=False), \
         patch("ui.dialogs.widget_manager.QMessageBox.warning") as warn:
        dlg.save_btn.click()
    warn.assert_called_once()
    assert dlg.result() != QDialog.Accepted


def test_huy_khong_ghi_file(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    with patch("ui.dialogs.widget_manager.UiConfigManager.save_ui_config") as save:
        dlg.cancel_btn.click()  # chưa đổi gì → đóng luôn, không hỏi
    save.assert_not_called()
    assert dlg.result() == QDialog.Rejected


def test_dong_khi_con_thay_doi_hoi_truoc(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.show()
    dlg.select("tools", "custom_1")
    dlg.up_btn.click()
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=NO) as ask:
        dlg.close()
    ask.assert_called_once()
    assert dlg.isVisible()
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=YES):
        dlg.close()
    assert not dlg.isVisible()


def test_sua_lan_hai_thay_calibration_chua_luu(qapp, qtbot, layout):
    """Sửa Bè bật Bypass rồi sửa lại Bè: Builder phải thấy Bypass đang chờ lưu,
    không đọc giá trị cũ trên đĩa rồi ghi đè mất."""
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "btn_be")
    first = _fake_builder(dict(dlg.working["tools"][4]), {"toggle_invert": {"be": True}})
    with patch("ui.dialogs.widget_manager.WidgetBuilderDialog", first):
        dlg.edit_btn.click()
    second = _fake_builder(dict(dlg.working["tools"][4]), None)
    with patch("ui.dialogs.widget_manager.WidgetBuilderDialog", second):
        dlg.edit_btn.click()
    assert second.call_args.kwargs["pending_calibration"] == {"toggle_invert": {"be": True}}
