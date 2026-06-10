import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication
from frontend_qt import MainDashboard

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def mock_engine():
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng_instance = mock_eng.return_value
        eng_instance.current_youtube_url = "http://yt.com"
        eng_instance.tone_detection_active = False
        eng_instance.autokey_active = False
        eng_instance._tone_session = MagicMock()
        eng_instance._tone_session.is_active = False
        yield eng_instance

def test_main_dashboard_init(qapp, mock_engine, qtbot):
    # UI-01
    # Patch load_songs and other config stuff
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        
        dashboard = MainDashboard()
        qtbot.addWidget(dashboard)
        
        assert dashboard.windowTitle() == "Quang Lưu Studio"
        assert dashboard.engine == mock_engine

def test_main_dashboard_tone_result_signal(qapp, mock_engine, qtbot):
    # UI-02
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        
        dashboard = MainDashboard()
        qtbot.addWidget(dashboard)
        
        # Emit signal manually
        result = {"url": "http://yt.com", "title": "Test Title", "tone": "C Major", "scale": "Major", "key_idx": 0}
        dashboard._tone_result_signal.emit(result)
        
        # Check UI updates
        assert "Test Title" in dashboard._marquee_text
        assert dashboard.tone_combo.currentText() == "C"
        assert dashboard.scale_combo.currentText() == "Major"

def test_toggle_dev_mode_rebuilds_with_context_menus(qapp, mock_engine, qtbot):
    # UI-04: Bật Dev Mode không được crash (regression: UnboundLocalError Qt
    # do import cục bộ trong panel builder) và phải gắn CustomContextMenu
    # lên các widget của 3 panel mixer/tools/mode.
    from PySide6.QtCore import Qt
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):

        dashboard = MainDashboard()
        qtbot.addWidget(dashboard)

        dashboard._toggle_dev_mode()  # crash ở đây nếu panel builder lỗi
        assert dashboard.is_dev_mode is True

        for ch_view in dashboard._mixer_channels.values():
            assert ch_view.contextMenuPolicy() == Qt.CustomContextMenu
        for btn in dashboard._mode_buttons.values():
            assert btn.contextMenuPolicy() == Qt.CustomContextMenu
        panel_btns = [b for b in dashboard._func_buttons.values()
                      if b.contextMenuPolicy() == Qt.CustomContextMenu]
        assert panel_btns, "Panel TOOLS phải có nút gắn context menu trong dev mode"

        # Tắt dev mode → rebuild lại bình thường
        dashboard._toggle_dev_mode()
        assert dashboard.is_dev_mode is False
        for ch_view in dashboard._mixer_channels.values():
            assert ch_view.contextMenuPolicy() == Qt.DefaultContextMenu


def test_quick_score_button(qapp, mock_engine, qtbot):
    # UI-03
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        
        dashboard = MainDashboard()
        qtbot.addWidget(dashboard)
        
        # Init state
        mock_engine.quick_score_active = False
        
        dashboard._on_score()
        mock_engine.start_quick_score.assert_called_once()
        
        mock_engine.quick_score_active = True
        dashboard._on_score()
        mock_engine.stop_quick_score.assert_called_once()
