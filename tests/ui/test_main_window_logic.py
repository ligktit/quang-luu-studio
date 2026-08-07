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


_STD_KEY_MAP = {
    "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
    "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
}


def test_reverse_lookup_key_standard_map():
    # Map chuẩn tuyến tính → khớp chính xác từng nốt
    for k, v in _STD_KEY_MAP.items():
        assert MainDashboard._reverse_lookup_key(v, _STD_KEY_MAP) == k


def test_reverse_lookup_key_nearest_when_offset():
    # Value lệch nhẹ → chọn nốt GẦN nhất
    assert MainDashboard._reverse_lookup_key(7, _STD_KEY_MAP) == "G"
    # 6.x làm tròn về phía gần hơn (value nguyên 6 -> F#)
    assert MainDashboard._reverse_lookup_key(6, _STD_KEY_MAP) == "F#"


def test_reverse_lookup_key_tie_prefers_exact():
    # Map bất thường: C và D cùng cách value=1 một khoảng, nhưng C# khớp chính xác.
    weird = dict(_STD_KEY_MAP)
    weird["C"] = 0   # diff 1
    weird["C#"] = 1  # diff 0 (exact)
    weird["D"] = 2   # diff 1
    assert MainDashboard._reverse_lookup_key(1, weird) == "C#"


def test_reverse_lookup_key_inverted_map():
    # Map ĐẢO chiều (value cao = nốt thấp) vẫn lấy đúng nốt gần nhất.
    inverted = {k: (11 - v) for k, v in _STD_KEY_MAP.items()}
    assert MainDashboard._reverse_lookup_key(11, inverted) == "C"
    assert MainDashboard._reverse_lookup_key(0, inverted) == "B"


def test_reverse_lookup_scale_nearest():
    smap = {"Major": 13, "Minor": 18}
    assert MainDashboard._reverse_lookup_scale(13, smap) == "Major"
    assert MainDashboard._reverse_lookup_scale(18, smap) == "Minor"
    assert MainDashboard._reverse_lookup_scale(17, smap) == "Minor"
    assert MainDashboard._reverse_lookup_scale(14, smap) == "Major"


def test_reverse_lookup_scale_guard_equal():
    # Major == Minor (map hỏng) → guard trả Major, không chia nhầm.
    assert MainDashboard._reverse_lookup_scale(20, {"Major": 20, "Minor": 20}) == "Major"


def test_is_speaker_loopback_error():
    assert MainDashboard._is_speaker_loopback_error(
        "Loa 'X' không phát ra âm thanh (im lặng).")
    assert MainDashboard._is_speaker_loopback_error(
        "...và phương án nghe loa cũng thất bại: ...")
    assert not MainDashboard._is_speaker_loopback_error(
        "Không tải được audio từ YouTube (video bị chặn).")


def test_mode_buttons_send_configured_cc(qapp, mock_engine, qtbot):
    # Regression: nút MODE (Dân Ca/Lofi/Remix/Đa Thể Loại) dùng action
    # "set_mode_*" nhưng handler thật là _on_mode_selected — không có
    # _on_set_mode_lofi. Trước fix, getattr trượt → nút rơi xuống nhánh
    # custom với cc=None → send_midi(None, 127) fail, DAW không đổi mode.
    from PySide6.QtCore import Qt
    import backend

    dashboard = _make_dashboard(qtbot)
    mode_cfg = backend.AppConfig.get_mode_config()

    for label, btn in dashboard._mode_buttons.items():
        expected_cc = int(mode_cfg[label]["cc"])
        on_val = int(mode_cfg[label].get("on_value", 127))
        off_val = int(mode_cfg[label].get("off_value", 0))

        # Bật
        dashboard.current_mode = None
        mock_engine.send_midi.reset_mock()
        qtbot.mouseClick(btn, Qt.LeftButton)
        assert dashboard.current_mode == label
        mock_engine.send_midi.assert_called_once_with(expected_cc, on_val)

        # Bấm lại → toggle tắt
        mock_engine.send_midi.reset_mock()
        qtbot.mouseClick(btn, Qt.LeftButton)
        assert dashboard.current_mode is None
        mock_engine.send_midi.assert_called_once_with(expected_cc, off_val)

    # Không nút nào được gửi CC None (triệu chứng của bug cũ)
    assert not [c for c in mock_engine.send_midi.call_args_list if c.args[0] is None]


def test_be_button_toggles_cc(qapp, mock_engine, qtbot):
    # Nút Bè (TOOLS): toggle bật/tắt hiệu ứng bè qua CC "be".
    from PySide6.QtCore import Qt
    import backend

    dashboard = _make_dashboard(qtbot)
    expected_cc = int(backend.AppConfig.get_midi_cc()["be"])

    btn = dashboard._func_buttons.get("Bè")
    assert btn is not None, "Panel TOOLS phải dựng được nút Bè"
    # Mặc định tắt
    assert dashboard.be_state is False
    assert btn._active is False

    mock_engine.send_midi.reset_mock()
    qtbot.mouseClick(btn, Qt.LeftButton)
    assert dashboard.be_state is True
    assert btn._active is True
    mock_engine.send_midi.assert_called_once_with(expected_cc, 127)

    mock_engine.send_midi.reset_mock()
    qtbot.mouseClick(btn, Qt.LeftButton)
    assert dashboard.be_state is False
    assert btn._active is False
    mock_engine.send_midi.assert_called_once_with(expected_cc, 0)


def test_be_button_syncs_from_midi(qapp, mock_engine, qtbot):
    # Studio One đổi state → nút Bè sáng/tắt theo (feedback ngược).
    import backend

    dashboard = _make_dashboard(qtbot)
    cc = int(backend.AppConfig.get_midi_cc()["be"])
    btn = dashboard._func_buttons["Bè"]

    dashboard._on_midi_cc_received(cc,127)
    assert dashboard.be_state is True
    assert btn._active is True

    dashboard._on_midi_cc_received(cc,0)
    assert dashboard.be_state is False
    assert btn._active is False


def test_be_cc_not_shared_with_other_controls(qapp, mock_engine, qtbot):
    # CC của Bè phải RIÊNG — trùng số với nút khác thì bấm cái này sẽ
    # lật trạng thái cái kia (đúng lỗi 'shared CC' từng gặp ở tone_auto/fix_meo).
    import backend
    cc_map = backend.AppConfig.get_midi_cc()
    others = [k for k, v in cc_map.items() if v == cc_map["be"] and k != "be"]
    assert not others, f"CC {cc_map['be']} của Bè bị dùng chung với: {others}"


def test_tat_on_button_toggles_cc(qapp, mock_engine, qtbot):
    # Nút Tắt Ồn (TOOLS): toggle khử ồn mic qua CC "tat_on" — có ở MỌI phiên bản.
    from PySide6.QtCore import Qt
    import backend

    dashboard = _make_dashboard(qtbot)
    expected_cc = int(backend.AppConfig.get_midi_cc()["tat_on"])

    btn = dashboard._func_buttons.get("Tắt Ồn")
    assert btn is not None, "Panel TOOLS phải dựng được nút Tắt Ồn"
    assert dashboard.tat_on_state is False
    assert btn._active is False

    mock_engine.send_midi.reset_mock()
    qtbot.mouseClick(btn, Qt.LeftButton)
    assert dashboard.tat_on_state is True
    assert btn._active is True
    mock_engine.send_midi.assert_called_once_with(expected_cc, 127)

    mock_engine.send_midi.reset_mock()
    qtbot.mouseClick(btn, Qt.LeftButton)
    assert dashboard.tat_on_state is False
    assert btn._active is False
    mock_engine.send_midi.assert_called_once_with(expected_cc, 0)


def test_tat_on_button_syncs_from_midi(qapp, mock_engine, qtbot):
    # Studio One đổi state → nút Tắt Ồn sáng/tắt theo (feedback ngược).
    import backend

    dashboard = _make_dashboard(qtbot)
    cc = int(backend.AppConfig.get_midi_cc()["tat_on"])
    btn = dashboard._func_buttons["Tắt Ồn"]

    dashboard._on_midi_cc_received(cc, 127)
    assert dashboard.tat_on_state is True
    assert btn._active is True

    dashboard._on_midi_cc_received(cc, 0)
    assert dashboard.tat_on_state is False
    assert btn._active is False


def test_tat_on_cc_not_shared_with_other_controls(qapp, mock_engine, qtbot):
    # CC riêng — trùng số với nút khác thì bấm cái này lật trạng thái cái kia.
    import backend
    cc_map = backend.AppConfig.get_midi_cc()
    others = [k for k, v in cc_map.items() if v == cc_map["tat_on"] and k != "tat_on"]
    assert not others, f"CC {cc_map['tat_on']} của Tắt Ồn bị dùng chung với: {others}"


# ── Vang tự động theo nhạc (Premium) ────────────────────────────────────────

def _auto_echo_dashboard(qtbot, premium=True, enabled=True):
    dashboard = _make_dashboard(qtbot)
    dashboard.settings["auto_echo_enabled"] = enabled
    patcher = patch("core.entitlements.has_feature",
                    side_effect=lambda name: premium or name != "auto_echo")
    patcher.start()
    qtbot.addWidget(dashboard)
    dashboard._set_reverb_muted = MagicMock()
    return dashboard, patcher


def _stop_auto_echo(dashboard, patcher):
    """Dừng timer thật + gỡ patch entitlements sau mỗi test."""
    dashboard.settings["auto_echo_enabled"] = False
    if dashboard._auto_echo_timer is not None:
        dashboard._auto_echo_timer.stop()
        dashboard._auto_echo_timer = None
    patcher.stop()


def test_auto_echo_requires_premium(qapp, mock_engine, qtbot):
    # Standard bật thiết lập cũng KHÔNG chạy vòng theo dõi nhạc.
    dashboard, patcher = _auto_echo_dashboard(qtbot, premium=False)
    try:
        dashboard._apply_auto_echo_setting()
        assert dashboard._auto_echo_timer is None
    finally:
        patcher.stop()


def test_auto_echo_off_when_setting_disabled(qapp, mock_engine, qtbot):
    # Premium nhưng chưa bật trong Cài đặt → không theo dõi.
    dashboard, patcher = _auto_echo_dashboard(qtbot, premium=True, enabled=False)
    try:
        dashboard._apply_auto_echo_setting()
        assert dashboard._auto_echo_timer is None
    finally:
        patcher.stop()


def test_auto_echo_opens_and_closes_reverb(qapp, mock_engine, qtbot):
    # Premium + bật: có nhạc → mở Vang; hết nhạc (đủ số nhịp) → tắt Vang.
    dashboard, patcher = _auto_echo_dashboard(qtbot, premium=True)
    try:
        dashboard._music_is_playing = MagicMock(return_value=False)
        dashboard._apply_auto_echo_setting()
        assert dashboard._auto_echo_timer is not None
        assert dashboard._auto_echo_playing is False

        # Nhạc chạy → mở Vang ngay ở nhịp đầu
        dashboard._music_is_playing.return_value = True
        dashboard._auto_echo_tick()
        dashboard._set_reverb_muted.assert_called_once_with(False)

        # Nhạc dừng: các nhịp đầu chưa lật (chống rung khi tua/chuyển bài)
        dashboard._set_reverb_muted.reset_mock()
        dashboard._music_is_playing.return_value = False
        for _ in range(dashboard._AUTO_ECHO_OFF_TICKS - 1):
            dashboard._auto_echo_tick()
        dashboard._set_reverb_muted.assert_not_called()

        # Đủ số nhịp → tắt Vang
        dashboard._auto_echo_tick()
        dashboard._set_reverb_muted.assert_called_once_with(True)
    finally:
        _stop_auto_echo(dashboard, patcher)


def test_auto_echo_ignores_short_gap(qapp, mock_engine, qtbot):
    # Nhạc khựng 1 nhịp rồi chạy lại → KHÔNG được tắt Vang.
    dashboard, patcher = _auto_echo_dashboard(qtbot, premium=True)
    try:
        dashboard._music_is_playing = MagicMock(return_value=True)
        dashboard._apply_auto_echo_setting()
        assert dashboard._auto_echo_playing is True

        dashboard._music_is_playing.return_value = False
        dashboard._auto_echo_tick()
        dashboard._music_is_playing.return_value = True
        dashboard._auto_echo_tick()

        dashboard._set_reverb_muted.assert_not_called()
        assert dashboard._auto_echo_playing is True
    finally:
        _stop_auto_echo(dashboard, patcher)


def test_auto_echo_reverb_mute_uses_mixer_button(qapp, mock_engine, qtbot):
    # _set_reverb_muted phải đi qua nút mute của Mixer (đồng bộ UI + CC phụ),
    # và không bấm lại khi trạng thái đã đúng.
    dashboard = _make_dashboard(qtbot)
    ch = dashboard._mixer_channels["mix_reverb"]

    assert ch.is_muted() is False
    dashboard._set_reverb_muted(True)
    assert ch.is_muted() is True
    assert dashboard.mute_states["mix_reverb"] is True

    dashboard._set_reverb_muted(True)   # gọi lại: không đổi gì
    assert ch.is_muted() is True

    dashboard._set_reverb_muted(False)
    assert ch.is_muted() is False


def test_music_is_playing_prefers_embedded_player(qapp, mock_engine, qtbot):
    # Player nhúng phát bằng QMediaPlayer thì WinRT/CDP không thấy → phải hỏi
    # thẳng cửa sổ player.
    dashboard = _make_dashboard(qtbot)
    mock_engine.cdp_monitor.is_connected = True
    mock_engine.cdp_monitor.is_playing = False
    mock_engine.media_monitor.is_playing = False

    assert dashboard._music_is_playing() is False

    dashboard._player_window = MagicMock()
    dashboard._player_window.is_playing.return_value = True
    assert dashboard._music_is_playing() is True
    dashboard._player_window = None


def test_quick_score_button(qapp, mock_engine, qtbot):
    # UI-03
    # Chấm điểm là tính năng Premium → phải giả lập quyền, nếu không test chỉ
    # pass trên máy đang cắm license Premium (máy Standard sẽ ra dialog upsell).
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("core.entitlements.has_feature", return_value=True), \
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
