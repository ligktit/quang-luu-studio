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


# ── EditSongDialog: lối tắt "Đặt 1 tone cho cả bài" ──────────────────────

def _make_dashboard_widget(qtbot):
    """Parent thật (QWidget) cho dialog, nhưng _show_message là mock để assert."""
    from PySide6.QtWidgets import QWidget
    dashboard = QWidget()
    qtbot.addWidget(dashboard)
    dashboard._show_message = MagicMock()
    return dashboard


def _make_edit_dialog(qtbot, song):
    from ui.dialogs.edit_song import EditSongDialog
    dashboard = _make_dashboard_widget(qtbot)
    with patch("backend.ManualToneTimeline.load_timeline", return_value=None):
        dlg = EditSongDialog(dashboard, song)
    qtbot.addWidget(dlg)
    return dlg, dashboard


def test_edit_song_quick_single_tone_saves_one_human_entry(qapp, qtbot):
    song = {"url": "http://yt/x", "title": "Bài Test", "id": 7, "tone": "C"}
    dlg, dashboard = _make_edit_dialog(qtbot, song)

    dlg._quick_key_combo.setCurrentText("G")
    dlg._quick_scale_combo.setCurrentText("Minor")

    with patch("backend.ManualToneTimeline.save_timeline", return_value=True) as mock_save, \
         patch("backend.SongManager.update_song") as mock_update, \
         patch("ui.dialogs.songs_list.SongsListDialog"):
        dlg._on_apply_single_tone()

    # Lưu đúng 1 mốc tại 0:00, source="human", key_display = Gm
    args, kwargs = mock_save.call_args
    url_arg, title_arg, entries_arg = args[0], args[1], args[2]
    assert url_arg == "http://yt/x"
    assert kwargs.get("source") == "human"
    assert len(entries_arg) == 1
    assert entries_arg[0]["time"] == 0.0
    assert entries_arg[0]["key_display"] == "Gm"
    assert entries_arg[0]["scale"] == "Minor"
    mock_update.assert_called_once()


def test_edit_song_quick_prefills_from_existing(qapp, qtbot):
    # Mốc đầu là Am → quick combos điền sẵn A + Minor
    song = {"url": "http://yt/y", "title": "T", "id": 1, "tone": "Am"}
    from ui.dialogs.edit_song import EditSongDialog
    dashboard = _make_dashboard_widget(qtbot)
    tl = {"timeline": [{"time": 0.0, "key_display": "Am", "key_index": 9, "scale": "Minor"}]}
    with patch("backend.ManualToneTimeline.load_timeline", return_value=tl):
        dlg = EditSongDialog(dashboard, song)
    qtbot.addWidget(dlg)
    assert dlg._quick_key_combo.currentText() == "A"
    assert dlg._quick_scale_combo.currentText() == "Minor"
