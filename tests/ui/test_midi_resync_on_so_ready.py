"""Bắn lại MIDI khi Studio One dựng xong cửa sổ.

Cổng MIDI ảo mở được ngay cả khi Studio One chưa chạy → `is_midi_connected()`
bật True từ giây đầu và lượt đồng bộ lúc khởi động bắn vào khoảng không. Bộ test
này chốt phần nối dây phía UI: watcher được bật, signal về đúng main thread, và
lượt đồng bộ đẩy đủ mode / vang / tone / mức mixer.
"""
from unittest.mock import MagicMock, patch

import pytest

from frontend_qt import MainDashboard


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def mock_engine():
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = "http://yt.com"
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        yield eng


def _make_dashboard(qtbot):
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard()
        qtbot.addWidget(dashboard)
        return dashboard


def test_watcher_duoc_bat_luc_khoi_dong(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    assert dashboard._so_ready_watcher is not None
    assert dashboard._so_ready_watcher.is_running() is True
    dashboard._so_ready_watcher.stop()


def test_signal_so_ready_chay_lai_dong_bo(qapp, mock_engine, qtbot):
    # Watcher chạy ở thread nền nên phải đi qua signal về main thread; ở đây
    # kiểm phần nối dây signal -> slot -> _sync_midi_states.
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()

    with patch.object(dashboard, "_sync_midi_states") as sync:
        dashboard._so_ready_signal.emit()
    sync.assert_called_once()


def test_dong_bo_gui_muc_thanh_truot_mixer(qapp, mock_engine, qtbot):
    # Thiếu bước này thì Studio One giữ nguyên mức của bản mẫu .song trong khi
    # giao diện hiển thị mức khác — ca "vang không ăn" hay gặp nhất.
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    assert dashboard._mixer_senders, "Panel mixer phải đăng ký hàm gửi cho từng kênh"

    sent = {}
    for cc_key in list(dashboard._mixer_senders):
        dashboard._mixer_senders[cc_key] = lambda v, k=cc_key: sent.__setitem__(k, v)

    dashboard._sync_midi_states()

    assert set(sent) == set(dashboard._mixer_senders)
    for cc_key, value in sent.items():
        assert value == dashboard._mixer_sliders[cc_key].value()


def test_dong_bo_gui_tone_va_the(qapp, mock_engine, qtbot):
    import backend
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    dashboard.current_tone = "F"
    dashboard.current_scale = "Minor"

    mock_engine.send_midi_pair.reset_mock()
    dashboard._sync_midi_states()

    cc = backend.AppConfig.get_midi_cc()
    key_cc = int(cc.get("key_root", 33))
    scale_cc = int(cc.get("scale_type", cc.get("key_scale", 35)))
    key_val = backend.AppConfig.get_key_midi_map()["F"]
    scale_val = backend.AppConfig.get_scale_midi_map()["Minor"]
    mock_engine.send_midi_pair.assert_any_call(key_cc, key_val, scale_cc, scale_val)


def test_dong_bo_khong_bat_co_chinh_tay(qapp, mock_engine, qtbot):
    # Đồng bộ máy móc KHÔNG được đi qua _on_tone_selected: hàm đó kéo theo
    # _lock_replay_for_manual_override, sẽ dừng replay timeline oan.
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    dashboard._manual_tone_override = False
    mock_engine.stop_tone_detection.reset_mock()

    dashboard._sync_midi_states()

    assert dashboard._manual_tone_override is False
    mock_engine.stop_tone_detection.assert_not_called()


def test_dong_bo_van_gui_mode_va_tat_vang(qapp, mock_engine, qtbot):
    # Hai thứ user nêu đích danh: lệnh chuyển mode và vang.
    import backend
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    dashboard.mode_states = {"Lofi": True}
    dashboard.mute_states["mix_reverb"] = True

    mock_engine.send_midi.reset_mock()
    dashboard._sync_midi_states()

    sent = {c.args[0]: c.args[1] for c in mock_engine.send_midi.call_args_list}
    mode_cfg = backend.AppConfig.get_mode_config()
    assert sent[int(mode_cfg["Lofi"]["cc"])] == int(mode_cfg["Lofi"]["on_value"])
    assert sent[int(mode_cfg["Remix"]["cc"])] == int(mode_cfg["Remix"]["off_value"])
    assert sent[int(backend.AppConfig.get_midi_cc()["mute_reverb"])] == 127


def test_dong_bo_lap_lai_cho_cung_ket_qua(qapp, mock_engine, qtbot):
    # CC là lệnh idempotent — watcher bắn lại nhiều mốc nên gọi hai lần phải ra
    # đúng cùng một bộ lệnh, không tự lật trạng thái nút nào.
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    dashboard.mode_states = {"Lofi": True, "Remix": False}

    mock_engine.send_midi.reset_mock()
    dashboard._sync_midi_states()
    first = {c.args[0]: c.args[1] for c in mock_engine.send_midi.call_args_list}

    mock_engine.send_midi.reset_mock()
    dashboard._sync_midi_states()
    second = {c.args[0]: c.args[1] for c in mock_engine.send_midi.call_args_list}

    assert first == second
    assert dashboard.mode_states["Lofi"] is True
    assert dashboard.mode_states["Remix"] is False


def test_dong_bo_loi_o_mot_nhom_khong_chan_nhom_khac(qapp, mock_engine, qtbot):
    # Một kênh mixer hỏng không được nuốt luôn các kênh còn lại.
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    ok = []
    keys = list(dashboard._mixer_senders)
    assert len(keys) >= 2

    def _boom(_v):
        raise RuntimeError("kênh hỏng")

    dashboard._mixer_senders[keys[0]] = _boom
    for k in keys[1:]:
        dashboard._mixer_senders[k] = lambda v, kk=k: ok.append(kk)

    dashboard._sync_midi_states()

    assert ok == keys[1:]
