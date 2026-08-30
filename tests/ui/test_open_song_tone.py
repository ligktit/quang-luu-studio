"""
tests/ui/test_open_song_tone.py
===============================
Mở bài ở ĐƯỜNG NÀO cũng phải chạy tone đã lưu, không để engine dò lại.

  U-01..U-03  _save_single_tone_timeline — ghi tone khách tự chọn, không đè
              chuỗi nhiều mốc
  U-04..U-05  _saved_manual_timeline — chuỗi thủ công → tone bài đã lưu
  U-06..U-07  play_youtube_in_app (dán link / ô tìm kiếm) truyền tone đã lưu
              cho engine thay vì xoá timeline rồi dò lại
  U-08        Danh sách bài hát → nút Phát đi qua cùng một đường
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from core.tone_cache import ManualToneTimeline, make_timeline_entry
from frontend_qt import MainDashboard

VIDEO_ID  = "abcdefghijk"
WATCH_URL = f"https://www.youtube.com/watch?v={VIDEO_ID}"
SHARE_URL = f"https://youtu.be/{VIDEO_ID}?si=XyZ123"


@pytest.fixture(autouse=True)
def isolated_data(tmp_path):
    songs_file = tmp_path / "saved_songs.json"
    songs_file.write_text("[]", encoding="utf-8")
    with patch("core.tone_cache.MANUAL_TIMELINES_FILE",
               str(tmp_path / "manual_timelines.json")), \
         patch("core.tone_cache.ToneCacheManager.CACHE_FILE",
               str(tmp_path / "tone_cache.json")), \
         patch("core.songs.SONGS_FILE", str(songs_file)):
        yield songs_file


def _write_songs(path, songs):
    path.write_text(json.dumps(songs, ensure_ascii=False), encoding="utf-8")


def _dashboard_stub(embedded=False):
    """Stub đủ dùng cho play_youtube_in_app — khỏi dựng cả MainDashboard."""
    stub = MagicMock()
    stub._saved_manual_timeline = MainDashboard._saved_manual_timeline
    stub._embedded_player_active.return_value = embedded
    return stub


# ── U-01..U-03 — ghi tone khách tự chọn ────────────────────────────────────

def test_save_single_tone_writes_human_entry(isolated_data):
    """U-01: chọn tone ở ô Tone khi lưu bài → có chuỗi tone thủ công 1 mốc để
    lần sau mở bài chạy đúng tone đó."""
    assert MainDashboard._save_single_tone_timeline(WATCH_URL, "Bài A", "Am") is True

    saved = ManualToneTimeline.load_timeline(WATCH_URL)
    assert saved["source"] == "human"
    assert saved["timeline"] == [make_timeline_entry("Am")]


def test_save_single_tone_never_overwrites_multi_entry_chain(isolated_data):
    """U-02: bài đã có chuỗi NHIỀU mốc do khách dựng → không được đè bằng 1 tone."""
    chain = [make_timeline_entry("Am"), make_timeline_entry("C", at=60)]
    ManualToneTimeline.save_timeline(WATCH_URL, "Bài A", chain, source="human")

    assert MainDashboard._save_single_tone_timeline(WATCH_URL, "Bài A", "G") is False
    assert ManualToneTimeline.load_timeline(WATCH_URL)["timeline"] == chain


def test_save_single_tone_needs_url_and_tone(isolated_data):
    """U-03: thiếu URL hoặc tone → không ghi gì, không ném lỗi."""
    assert MainDashboard._save_single_tone_timeline("", "Bài A", "Am") is False
    assert MainDashboard._save_single_tone_timeline(WATCH_URL, "Bài A", "") is False


# ── U-04..U-05 — chuỗi tone đã lưu của một URL ─────────────────────────────

def test_saved_timeline_prefers_manual_chain(isolated_data):
    """U-04: có chuỗi thủ công → dùng chuỗi đó (không phải tone đơn của bài)."""
    _write_songs(isolated_data, [{"id": 1, "url": WATCH_URL, "tone": "G", "title": "A"}])
    chain = [make_timeline_entry("Am"), make_timeline_entry("F", at=90)]
    ManualToneTimeline.save_timeline(WATCH_URL, "A", chain, source="human")

    assert MainDashboard._saved_manual_timeline(SHARE_URL) == chain


def test_saved_timeline_falls_back_to_song_tone(isolated_data):
    """U-05: chưa có chuỗi → lấy tone khách đã lưu ở Danh sách bài hát."""
    _write_songs(isolated_data, [{"id": 1, "url": WATCH_URL, "tone": "Am", "title": "A"}])
    assert MainDashboard._saved_manual_timeline(SHARE_URL) == [make_timeline_entry("Am")]
    assert MainDashboard._saved_manual_timeline("https://youtu.be/zzzzzzzzzzz") is None


# ── U-06..U-07 — dán link / ô tìm kiếm ─────────────────────────────────────

def test_play_by_url_replays_saved_tone(isolated_data):
    """U-06: ĐIỂM MÙ — mở bài bằng link ở chế độ trình duyệt trước đây xoá sạch
    timeline rồi để engine dò lại. Nay phải trao thẳng chuỗi tone đã lưu."""
    chain = [make_timeline_entry("Am"), make_timeline_entry("C", at=60)]
    ManualToneTimeline.save_timeline(WATCH_URL, "Bài A", chain, source="human")

    stub = _dashboard_stub()
    MainDashboard.play_youtube_in_app(stub, SHARE_URL)

    kwargs = stub.engine.open_youtube_url.call_args.kwargs
    assert kwargs["manual_timeline"] == chain
    stub._set_tone_timeline.assert_called_once_with(chain, 0.0)
    stub._clear_tone_timeline.assert_not_called()


def test_play_by_url_unknown_song_clears_timeline(isolated_data):
    """U-07: bài lạ → vẫn xoá timeline bài trước (không để mốc bài cũ rò sang)."""
    stub = _dashboard_stub()
    MainDashboard.play_youtube_in_app(stub, WATCH_URL)

    assert stub.engine.open_youtube_url.call_args.kwargs["manual_timeline"] is None
    stub._clear_tone_timeline.assert_called_once()


# ── U-08 — Danh sách bài hát → nút Phát ────────────────────────────────────

def test_songs_list_play_uses_saved_tone(qapp, qtbot, isolated_data):
    """U-08: bài lưu tone bằng ô Tone (chưa từng sửa chuỗi) — nút Phát vẫn phải
    gửi tone đó cho engine, không mở bài trắng tone rồi chờ dò."""
    from PySide6.QtWidgets import QComboBox
    from core.tone_cache import CHROMATIC_NOTES
    from ui.dialogs.songs_list import SongsListDialog

    _write_songs(isolated_data, [{"id": 1, "url": WATCH_URL, "tone": "Am", "title": "Bài A"}])
    song = {"id": 1, "url": WATCH_URL, "tone": "Am", "title": "Bài A"}

    combo = QComboBox()
    qtbot.addWidget(combo)
    combo.addItems(CHROMATIC_NOTES)   # ô tone thật: chỉ 12 nốt gốc
    combo.setCurrentText("C")

    dash = _dashboard_stub()
    dash._waveform = None
    dash.tone_combo = combo
    dlg_stub = MagicMock()
    dlg_stub._dashboard = dash

    SongsListDialog._make_play(dlg_stub, song)()

    kwargs = dash.engine.open_youtube_url.call_args.kwargs
    assert kwargs["manual_timeline"] == [make_timeline_entry("Am")]
    # "Am" phải hiện thành "A" chứ không rơi vào hư không (giữ nguyên tone bài trước).
    assert combo.currentText() == "A"
