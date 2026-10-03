"""Thiết lập theo bài: reset khi sang bài mới, lưu khi lưu bài, khôi phục khi mở lại.

  R-01..R-03  Sang bài mới: tone chốt tay, Tone Nhạc, Tone Giọng, MODE về mặc định
  R-04..R-07  Lưu → khôi phục (mọi đường mở bài, mọi gói), tone chốt tay
  R-08..R-10  Tone Nhạc ≠ 0: tone Auto-Tune gửi/hiển thị phải cộng độ dịch
  R-11        Engine chỉ báo đổi bài khi thật sự đổi bài
  R-12..R-13  Thanh "Giọng" (hiệu ứng em bé ↔ robot) có CC 54 riêng
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from frontend_qt import MainDashboard

URL_A = "https://www.youtube.com/watch?v=aaaaaaaaaaa"
URL_B = "https://www.youtube.com/watch?v=bbbbbbbbbbb"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def mock_engine():
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = URL_A
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng.key_locked = False
        eng.tone_transpose = 0
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        yield eng


@pytest.fixture(autouse=True)
def isolated_data(tmp_path):
    songs_file = tmp_path / "saved_songs.json"
    songs_file.write_text("[]", encoding="utf-8")
    with patch("core.songs.SONGS_FILE", str(songs_file)), \
         patch("core.songs.PLAYLISTS_FILE", str(tmp_path / "playlists.json")), \
         patch("core.tone_cache.MANUAL_TIMELINES_FILE", str(tmp_path / "manual.json")), \
         patch("core.tone_cache.ToneCacheManager.CACHE_FILE", str(tmp_path / "cache.json")):
        yield songs_file


@pytest.fixture
def premium():
    # Smart Recall đã mở cho mọi gói — fixture giữ lại để test không phụ thuộc
    # vào license thật của máy chạy test.
    with patch("core.entitlements.has_feature", return_value=True):
        yield


def _make_dashboard(qtbot):
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        dash = MainDashboard({"studio_one_path": "", "auto_close_studio_one": False})
        qtbot.addWidget(dash)
        if dash._so_ready_watcher is not None:
            dash._so_ready_watcher.stop()
        return dash


def _sent(engine):
    return [c.args for c in engine.send_midi.call_args_list]


def _cc(dash, key):
    return int(dash.MIDI_CC[key])


# ── R-01..R-03 — sang bài mới ─────────────────────────────────────────────

def test_sang_bai_moi_reset_tone_nhac_va_tone_giong(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    dash._set_tone_offset("tone_music", 3)
    dash._set_tone_offset("tone_voice", -2)
    mock_engine.send_midi.reset_mock()

    dash._on_song_changed(URL_B)

    assert dash.tone_music_value == 0 and dash.tone_voice_value == 0
    assert mock_engine.tone_transpose == 0
    assert (_cc(dash, "tone_music"), 63) in _sent(mock_engine)
    assert (_cc(dash, "tone_voice"), 63) in _sent(mock_engine)
    assert dash._tone_value_labels["tone_music"].text() == "+0"


def test_sang_bai_moi_khong_dich_tone_auto_tune_khi_reset(qapp, mock_engine, qtbot):
    # Reset Tone Nhạc KHÔNG được kéo tone Auto-Tune lùi theo: tone bài mới do
    # lượt dò quyết định, không phải tone bài cũ trừ đi độ dịch.
    dash = _make_dashboard(qtbot)
    dash._set_tone_offset("tone_music", 2)
    tone_before = dash.current_tone
    mock_engine.send_midi.reset_mock()

    dash._on_song_changed(URL_B)

    assert dash.current_tone == tone_before
    assert all(cc != _cc(dash, "key_root") for cc, _ in _sent(mock_engine))


def test_sang_bai_moi_go_khoa_tone_chinh_tay_va_timeline_cu(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    dash._set_tone_timeline([{"time": 0, "key_display": "C"},
                             {"time": 30, "key_display": "D"}], 100)
    dash._on_tone_selected("F")          # người dùng chốt tay ở bài A
    assert dash._manual_tone_override is True and mock_engine.key_locked is True

    dash._on_song_changed(URL_B)

    assert dash._manual_tone_override is False
    assert mock_engine.key_locked is False
    assert dash._tone_timeline == []


# ── R-04..R-07 — lưu rồi khôi phục ────────────────────────────────────────

def _setup_song_state(dash):
    dash._set_tone_offset("tone_music", 2)
    dash._set_tone_offset("tone_voice", -1)
    dash._set_mode("Lofi", True)
    dash._on_be()                                   # Bè: TẮT → BẬT
    dash._mixer_sliders["mix_mic"].setValue(4)


def _save_current_as(dash, url, title="Bài A", tone="C"):
    from core.songs import SongManager
    assert SongManager.add_song(title, url, tone, preset=dash._capture_current_preset())


def test_luu_bai_roi_mo_lai_tu_trinh_duyet_khoi_phuc_du(qapp, mock_engine, qtbot, premium):
    dash = _make_dashboard(qtbot)
    _setup_song_state(dash)
    _save_current_as(dash, URL_A)

    dash._on_song_changed(URL_B)                    # sang bài khác → mọi thứ reset
    assert dash.tone_music_value == 0 and dash.tone_voice_value == 0
    dash._set_mode("Lofi", False)
    dash._on_be()                                   # Bè về TẮT
    dash._mixer_sliders["mix_mic"].setValue(0)

    # Mở lại bài A bằng trình duyệt (không qua Danh sách bài hát), link rút gọn.
    restored = dash._on_song_changed("https://youtu.be/aaaaaaaaaaa?si=x")

    assert restored is True
    assert (dash.tone_music_value, dash.tone_voice_value) == (2, -1)
    assert mock_engine.tone_transpose == 2
    assert dash.mode_states.get("Lofi") is True
    assert dash.be_state is True
    assert dash._mixer_sliders["mix_mic"].value() == 4
    assert dash.current_title == "Bài A"


def test_goi_thuong_cung_duoc_khoi_phuc(qapp, mock_engine, qtbot):
    from core import entitlements
    dash = _make_dashboard(qtbot)
    _setup_song_state(dash)
    _save_current_as(dash, URL_A)
    dash._on_song_changed(URL_B)

    with patch("core.entitlements.is_premium", return_value=False):
        assert entitlements.has_feature("smart_recall") is True
        restored = dash._on_song_changed(URL_A)

    assert restored is True
    assert (dash.tone_music_value, dash.tone_voice_value) == (2, -1)


def test_sang_bai_moi_tat_het_mode(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    dash._set_mode("Lofi", True)
    dash._set_mode("Remix", True)
    mock_engine.send_midi.reset_mock()

    dash._on_song_changed(URL_B)

    assert dash.active_modes() == []
    modes = dash._get_mode_config()
    for name in ("Lofi", "Remix"):
        assert (int(modes[name]["cc"]), int(modes[name]["off_value"])) in _sent(mock_engine)


def test_mo_bai_da_luu_mode_khong_bi_tat_roi_bat_lai(qapp, mock_engine, qtbot, premium):
    # Bài lưu với Lofi BẬT, đang BẬT sẵn → mở bài không được gửi TẮT rồi BẬT
    # liền nhau (plugin chớp một nhịp): preset đã đặt MODE thì bỏ qua reset MODE.
    dash = _make_dashboard(qtbot)
    dash._set_mode("Lofi", True)
    _save_current_as(dash, URL_A)
    mock_engine.send_midi.reset_mock()

    dash.engine.forget_current_song = MagicMock()
    dash._on_song_changed(URL_A)

    lofi = dash._get_mode_config()["Lofi"]
    assert (int(lofi["cc"]), int(lofi["off_value"])) not in _sent(mock_engine)
    assert dash.mode_states["Lofi"] is True


def test_mode_tu_them_o_dev_mode_van_gui_cc_khi_reset(qapp, mock_engine, qtbot):
    ui_config = {"mode": [{"id": "c1", "type": "button", "label": "Bolero", "cc": 60,
                           "on_value": 127, "off_value": 0}]}
    dash = _make_dashboard(qtbot)
    dash._mode_buttons["Bolero"] = MagicMock()
    dash.mode_states["Bolero"] = True
    mock_engine.send_midi.reset_mock()
    with patch("frontend_qt.backend.UiConfigManager.load_ui_config", return_value=ui_config):
        dash._on_song_changed(URL_B)
    assert (60, 0) in _sent(mock_engine)


def test_tone_chot_tay_duoc_khoi_phuc_va_khong_bi_luot_do_de(qapp, mock_engine, qtbot, premium):
    dash = _make_dashboard(qtbot)
    dash._on_tone_selected("D")                     # chốt tay D
    _save_current_as(dash, URL_A, tone="D")
    dash._on_song_changed(URL_B)
    dash._sync_tone_widgets("G", "Major")

    dash._on_song_changed(URL_A)
    assert dash.tone_combo.currentText() == "D"
    assert mock_engine.key_locked is True

    # Lượt dò nền về sau với tone khác → KHÔNG được đè tone đã chốt.
    dash._handle_tone_result({"url": URL_A, "title": "Bài A", "key": "A",
                              "key_display": "A", "scale": "Major"})
    assert dash.tone_combo.currentText() == "D"
    assert dash._manual_tone_override is True


def test_tone_do_tu_dong_khong_bi_ep_thanh_mot_tone(qapp, mock_engine, qtbot, premium):
    # Bài lưu lúc tone do dò/chuỗi tone lo → mở lại KHÔNG khoá tone (giữ được
    # các mốc đổi tone giữa bài), lượt dò vẫn cập nhật bình thường.
    dash = _make_dashboard(qtbot)
    dash._sync_tone_widgets("E", "Minor")
    _save_current_as(dash, URL_A, tone="Em")
    dash._on_song_changed(URL_B)

    dash._on_song_changed(URL_A)
    assert dash._manual_tone_override is False
    assert mock_engine.key_locked is False
    assert dash.tone_combo.currentText() == "E"     # tone đã lưu hiện ngay

    dash._handle_tone_result({"url": URL_A, "title": "Bài A", "key": "F",
                              "key_display": "F", "scale": "Major"})
    assert dash.tone_combo.currentText() == "F"


def test_luu_bai_tu_hop_thoai_kem_thiet_lap(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    _setup_song_state(dash)
    preset = dash._capture_current_preset()
    with patch("frontend_qt.threading.Thread") as thread:
        dash._process_quick_save(URL_A, "C", "Bài A", preset=preset)
        thread.call_args.kwargs["target"]()
    from core.songs import SongManager
    saved = SongManager.get_preset(SongManager.find_song_by_url(URL_A)["id"])
    assert (saved["tone_music"], saved["tone_voice"]) == (2, -1)
    assert saved["modes"] == ["Lofi"]
    assert saved["toggles"]["be"] is True
    assert saved["mixer"]["mic"] == 4
    assert saved["v"] == 2


# ── R-08..R-10 — Tone Nhạc ≠ 0 ────────────────────────────────────────────

def test_bam_tone_nhac_dich_tone_auto_tune(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    dash._sync_tone_widgets("C", "Major")
    mock_engine.send_midi.reset_mock()

    dash._set_tone_offset("tone_music", 2)

    assert dash.current_tone == "D"
    key_map = __import__("backend").AppConfig.get_key_midi_map()
    assert (_cc(dash, "key_root"), key_map["D"]) in _sent(mock_engine)


def test_ket_qua_do_hien_tone_da_cong_tone_nhac(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    dash._set_tone_offset("tone_music", 2, shift_key=False)
    dash._handle_tone_result({"url": URL_A, "title": "Bài A", "key": "A",
                              "key_display": "Am", "scale": "Minor"})
    assert dash.tone_combo.currentText() == "B"


def test_engine_gui_tone_da_cong_do_dich_va_ton_trong_khoa():
    from core.engine._tone import _ToneMixin

    class Fake:
        def __init__(self):
            self.sent = []
            self.tone_transpose = 0
            self.key_locked = False

        def send_midi_pair(self, cc1, v1, cc2, v2):
            self.sent.append((cc1, v1))

    from core.config import AppConfig
    key_map = AppConfig.get_key_midi_map()
    eng = Fake()
    eng.tone_transpose = 2
    _ToneMixin._send_tone_midi(eng, {"key_index": 9, "scale": "Minor"})   # A → B
    assert eng.sent[-1][1] == key_map["B"]

    eng.tone_transpose = -3
    _ToneMixin._send_tone_midi(eng, {"key_index": 1, "scale": "Major"})   # C# → A#
    assert eng.sent[-1][1] == key_map["A#"]

    eng.key_locked = True
    _ToneMixin._send_tone_midi(eng, {"key_index": 0, "scale": "Major"})
    assert len(eng.sent) == 2


# ── R-11 — engine báo đổi bài ────────────────────────────────────────────

def test_engine_chi_bao_doi_bai_khi_that_su_doi_bai():
    from core.engine._youtube import _YouTubeMixin

    class Fake(_YouTubeMixin):
        pass

    eng = Fake()
    eng._current_song_url = None
    seen = []
    eng.on_song_changed = seen.append

    eng.note_current_song(URL_A)
    eng.note_current_song("https://youtu.be/aaaaaaaaaaa")   # cùng bài, link khác
    eng.note_current_song(URL_A + "&t=30")
    eng.note_current_song(URL_B)
    assert seen == [URL_A, URL_B]

    eng.forget_current_song()
    eng.note_current_song(URL_B)                             # chọn lại từ danh sách
    assert seen == [URL_A, URL_B, URL_B]


# ── R-12..R-13 — thanh "Giọng" (hiệu ứng em bé ↔ robot) ───────────────────

def test_thanh_giong_gui_cc_rieng_khong_dung_toi_tone_nhac(qapp, mock_engine, qtbot):
    dash = _make_dashboard(qtbot)
    assert int(dash.MIDI_CC["voice_fx"]) == 54
    ch = dash._mixer_channels["voice_fx"]
    mock_engine.send_midi.reset_mock()

    ch.slider.setValue(6)

    sent = _sent(mock_engine)
    assert (54, int((18 / 24) * 127)) in sent
    assert all(cc != _cc(dash, "tone_music") for cc, _ in sent)
    assert dash.tone_music_value == 0


def test_ui_config_cu_duoc_chuyen_sang_voice_fx(tmp_path):
    from core.config import UiConfigManager
    old = {"mixer": [{"id": "tone_music", "type": "slider", "label": "Giọng",
                      "cc": "tone_music", "range": [-12, 12], "hidden": False}],
           "tools": [], "mode": []}
    path = tmp_path / "ui_config.json"
    path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    with patch("core.config.UI_CONFIG_FILE", str(path)):
        cfg = UiConfigManager.load_ui_config()
    ids = [e["id"] for e in cfg["mixer"]]
    assert ids.count("voice_fx") == 1 and "tone_music" not in ids
    entry = next(e for e in cfg["mixer"] if e["id"] == "voice_fx")
    assert entry["cc"] == "voice_fx" and entry["label"] == "Giọng"


def test_ui_config_da_tu_gan_cc_so_thi_giu_nguyen(tmp_path):
    from core.config import UiConfigManager
    old = {"mixer": [{"id": "tone_music", "type": "slider", "label": "Giọng",
                      "cc": 70, "range": [-12, 12], "hidden": False}],
           "tools": [], "mode": []}
    path = tmp_path / "ui_config.json"
    path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    with patch("core.config.UI_CONFIG_FILE", str(path)):
        cfg = UiConfigManager.load_ui_config()
    kept = next(e for e in cfg["mixer"] if e["id"] == "tone_music")
    assert kept["cc"] == 70
