import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication
from frontend_qt import ActivationDialog

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def mock_activation_manager():
    with patch("frontend_qt.backend.ActivationManager") as mock_am:
        yield mock_am

def test_activation_dialog_init(qapp, mock_activation_manager):
    # D-01
    mock_activation_manager.get_days_remaining.return_value = 100
    dialog = ActivationDialog()
    assert dialog.windowTitle() == "Kích hoạt Quang Lưu Studio"

def test_activation_dialog_submit_empty(qapp, mock_activation_manager, qtbot):
    # D-02
    dialog = ActivationDialog()
    qtbot.addWidget(dialog)
    
    dialog.code_input.setText("")
    
    dialog._activate()
    assert "Vui lòng nhập" in dialog.status_label.text()
    assert not mock_activation_manager.activate.called

def test_activation_dialog_submit_valid(qapp, mock_activation_manager, qtbot):
    # D-03
    dialog = ActivationDialog()
    qtbot.addWidget(dialog)
    
    dialog.code_input.setText("VALID-CODE")
    mock_activation_manager.activate.return_value = {"success": True, "message": "OK"}
    
    dialog._activate()
    assert "Kích hoạt thành công" in dialog.status_label.text()
    mock_activation_manager.activate.assert_called_once_with("VALID-CODE")

def test_activation_dialog_submit_invalid(qapp, mock_activation_manager, qtbot):
    # D-04
    dialog = ActivationDialog()
    qtbot.addWidget(dialog)
    
    dialog.code_input.setText("INVALID-CODE")
    mock_activation_manager.activate.return_value = {"success": False, "message": "Error"}
    
    dialog._activate()
    assert "Mã không hợp lệ" in dialog.status_label.text()
