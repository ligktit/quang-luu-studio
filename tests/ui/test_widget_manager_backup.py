"""Xuất/Nhập file từ hộp Quản lý giao diện."""
import copy
import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from core import devmode_backup
from core.config import UiConfigManager
from ui.dialogs.widget_manager import WidgetManagerDialog

M = "ui.dialogs.widget_manager"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def dlg(qapp, qtbot):
    d = WidgetManagerDialog(None, panel_name="tools",
                            ui_config=copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG))
    qtbot.addWidget(d)
    return d


def test_xuat_file(dlg):
    with patch(f"{M}.QFileDialog.getSaveFileName", return_value=("D:/x.json", "")) as ask, \
         patch(f"{M}.devmode_backup.export_backup") as export, \
         patch(f"{M}.QMessageBox.information"):
        dlg.export_btn.click()
    assert ask.call_args.args[2].startswith("quangluu-giaodien-")
    export.assert_called_once_with("D:/x.json")


def test_xuat_khi_chua_luu_thi_nhac(dlg):
    dlg.select("tools", "btn_be")
    dlg.up_btn.click()
    with patch(f"{M}.QFileDialog.getSaveFileName") as ask, \
         patch(f"{M}.QMessageBox.information") as info:
        dlg.export_btn.click()
    ask.assert_not_called()
    info.assert_called_once()


def test_nhap_file_xac_nhan_roi_khoi_phuc(dlg):
    backup = {"ui_config": {"tools": []}, "calibration_overrides": {}}
    with patch(f"{M}.QFileDialog.getOpenFileName", return_value=("D:/x.json", "")), \
         patch(f"{M}.devmode_backup.read_backup", return_value=backup), \
         patch(f"{M}.devmode_backup.summarize", return_value="Tools: 0 widget"), \
         patch(f"{M}.devmode_backup.restore_backup", return_value=["a.bak"]) as restore, \
         patch(f"{M}.QMessageBox.question", return_value=QMessageBox.Yes) as ask:
        dlg.import_btn.click()
    assert "Tools: 0 widget" in ask.call_args.args[2]
    assert "sao lưu tự động" in ask.call_args.args[2]
    restore.assert_called_once_with(backup)
    assert dlg.restored and dlg.restored_backups == ["a.bak"]
    assert dlg.result() == QDialog.Accepted


def test_nhap_file_huy_khong_ghi(dlg):
    with patch(f"{M}.QFileDialog.getOpenFileName", return_value=("D:/x.json", "")), \
         patch(f"{M}.devmode_backup.read_backup", return_value={"ui_config": {}}), \
         patch(f"{M}.devmode_backup.summarize", return_value=""), \
         patch(f"{M}.devmode_backup.restore_backup") as restore, \
         patch(f"{M}.QMessageBox.question", return_value=QMessageBox.No):
        dlg.import_btn.click()
    restore.assert_not_called()
    assert not dlg.restored


def test_nhap_file_sai_bao_loi(dlg):
    err = devmode_backup.BackupError("File này không phải bản sao lưu")
    with patch(f"{M}.QFileDialog.getOpenFileName", return_value=("D:/x.json", "")), \
         patch(f"{M}.devmode_backup.read_backup", side_effect=err), \
         patch(f"{M}.devmode_backup.restore_backup") as restore, \
         patch(f"{M}.QMessageBox.warning") as warn:
        dlg.import_btn.click()
    assert "không phải bản sao lưu" in warn.call_args.args[2]
    restore.assert_not_called()


def test_nhap_khi_con_thay_doi_bao_se_bo(dlg):
    dlg.select("tools", "btn_be")
    dlg.up_btn.click()
    with patch(f"{M}.QFileDialog.getOpenFileName", return_value=("D:/x.json", "")), \
         patch(f"{M}.devmode_backup.read_backup", return_value={"ui_config": {}}), \
         patch(f"{M}.devmode_backup.summarize", return_value=""), \
         patch(f"{M}.devmode_backup.restore_backup", return_value=[]), \
         patch(f"{M}.QMessageBox.question", return_value=QMessageBox.Yes) as ask:
        dlg.import_btn.click()
    assert "chưa lưu" in ask.call_args.args[2]
    assert ask.call_count == 1  # accept() sau khi khôi phục không hỏi thêm
