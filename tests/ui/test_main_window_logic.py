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


def _make_dashboard(qtbot):
    """Helper: build a MainDashboard with config patched out."""
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard()
        qtbot.addWidget(dashboard)
        return dashboard


def test_toggle_relative_major_to_minor(qapp, mock_engine, qtbot):
    # Nút "Tương đối": C Major → A Minor (đổi cả root lẫn scale)
    dashboard = _make_dashboard(qtbot)
    dashboard.current_tone = "C"
    dashboard.current_scale = "Major"
    dashboard.tone_combo.setCurrentText("C")
    dashboard.scale_combo.setCurrentText("Major")

    dashboard._on_toggle_relative()

    assert dashboard.current_tone == "A"
    assert dashboard.current_scale == "Minor"
    assert dashboard.tone_combo.currentText() == "A"
    assert dashboard.scale_combo.currentText() == "Minor"


def test_toggle_relative_minor_to_major(qapp, mock_engine, qtbot):
    # A Minor → C Major (chiều ngược lại)
    dashboard = _make_dashboard(qtbot)
    dashboard.current_tone = "A"
    dashboard.current_scale = "Minor"
    dashboard.tone_combo.setCurrentText("A")
    dashboard.scale_combo.setCurrentText("Minor")

    dashboard._on_toggle_relative()

    assert dashboard.current_tone == "C"
    assert dashboard.current_scale == "Major"


def test_handle_tone_result_ignores_listening_status(qapp, mock_engine, qtbot):
    # Status 'listening'/'stopped' không được set combo (tránh nhấp nháy)
    dashboard = _make_dashboard(qtbot)
    dashboard.tone_combo.setCurrentText("D")
    marquee_before = dashboard._marquee_text

    dashboard._handle_tone_result({"status": "listening", "key_display": "..."})
    assert dashboard.tone_combo.currentText() == "D"

    dashboard._handle_tone_result({"status": "stopped"})
    assert dashboard.tone_combo.currentText() == "D"
    # Marquee không bị đổi bởi 2 sự kiện trên
    assert dashboard._marquee_text == marquee_before


def test_handle_tone_result_ignores_invalid_key(qapp, mock_engine, qtbot):
    # key_display lạ (Silence) → bỏ qua, không set combo
    dashboard = _make_dashboard(qtbot)
    dashboard.tone_combo.setCurrentText("E")
    dashboard._handle_tone_result({"key_display": "Silence", "key": "Silence"})
    assert dashboard.tone_combo.currentText() == "E"


def test_no_autosave_when_uncertain(qapp, mock_engine, qtbot):
    # Tone uncertain → KHÔNG tự lưu bài
    dashboard = _make_dashboard(qtbot)
    with patch("frontend_qt.backend.SongManager.add_song") as mock_add:
        dashboard._handle_tone_result({
            "url": "http://yt.com", "title": "Bài Test", "key": "C",
            "scale": "Major", "uncertain": True, "confidence_level": "low",
        })
        mock_add.assert_not_called()


def test_autosave_when_confident(qapp, mock_engine, qtbot):
    # Tone chắc chắn (dò mới, không cache) → tự lưu
    import time
    dashboard = _make_dashboard(qtbot)
    with patch("frontend_qt.backend.SongManager.add_song") as mock_add:
        dashboard._handle_tone_result({
            "url": "http://yt.com", "title": "Bài Test", "key": "C",
            "scale": "Major", "uncertain": False, "confidence_level": "high",
        })
        # auto_save chạy trong thread daemon → chờ ngắn
        for _ in range(50):
            if mock_add.called:
                break
            time.sleep(0.02)
        mock_add.assert_called_once()


def test_manual_tone_override_locks_replay(qapp, mock_engine, qtbot):
    # Chỉnh tone tay → gọi stop_tone_detection + bật cờ override
    dashboard = _make_dashboard(qtbot)
    dashboard._manual_tone_override = False
    dashboard._on_tone_selected("G")
    assert dashboard._manual_tone_override is True
    mock_engine.stop_tone_detection.assert_called()


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
