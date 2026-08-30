"""
tests/core/test_tone_resolve_saved.py
=====================================
Tone người dùng đã lưu phải THẮNG việc dò lại.

Bọc 4 điểm mù đã vá (xem docs/TONE_FLOWS.md §3):
  R-01..R-03  make_timeline_entry — 1 tên tone → 1 mốc timeline đúng nốt/thể
  R-04..R-07  tone bài đã lưu (saved_songs.json) vào được chuỗi resolve
  R-08..R-09  đệm resolve trong phiên: khóa theo video_id + tự bỏ khi dữ liệu đổi
  R-10..R-12  watcher so URL theo bài, không so chuỗi thô
  R-13..R-14  chế độ "dò toàn bài" dùng CHUNG chuỗi resolve với chế độ nhanh
"""
import json
import threading
from unittest.mock import MagicMock, patch

import pytest

import core.tone_cache as tone_cache
from core.tone_cache import (
    ManualToneTimeline,
    ToneCacheManager,
    make_timeline_entry,
    saved_tone_timeline,
    song_tone_entry,
)

VIDEO_ID   = "abcdefghijk"
WATCH_URL  = f"https://www.youtube.com/watch?v={VIDEO_ID}"
SHARE_URL  = f"https://youtu.be/{VIDEO_ID}?si=XyZ123"
LIST_URL   = f"https://www.youtube.com/watch?v={VIDEO_ID}&list=RDxyz&index=2"


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_data(tmp_path):
    """Mọi file dữ liệu (tone cache, timeline thủ công, danh sách bài) → tmp_path."""
    tone_file     = tmp_path / "tone_cache.json"
    timeline_file = tmp_path / "manual_timelines.json"
    songs_file    = tmp_path / "saved_songs.json"
    songs_file.write_text("[]", encoding="utf-8")

    with patch("core.tone_cache.ToneCacheManager.CACHE_FILE", str(tone_file)), \
         patch("core.tone_cache.MANUAL_TIMELINES_FILE", str(timeline_file)), \
         patch("core.songs.SONGS_FILE", str(songs_file)):
        yield {"tone": tone_file, "timeline": timeline_file, "songs": songs_file}


def _write_songs(path, songs):
    path.write_text(json.dumps(songs, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def engine(mocker):
    """SystemEngine với toàn bộ phần cứng/nền được mock (giống tests/core/test_engine.py)."""
    mocker.patch("core.engine.MidiHandler")
    mocker.patch("core.engine.AudioRecorder")
    mocker.patch("core.engine.WindowsMediaMonitor")
    mocker.patch("core.engine.MemoryProfiler")

    cdp_mock = mocker.patch("core.engine.CDPYouTubeMonitor")
    cdp_instance = MagicMock()
    cdp_instance.is_connected = False
    cdp_instance.target_url = None
    cdp_mock.return_value = cdp_instance

    mg_mock = mocker.patch("core.engine.MemoryGuard")
    mg_mock.return_value = MagicMock()

    # Thư viện tone cộng đồng: không đụng tới mạng trong test.
    mocker.patch("core.engine._tone._ToneMixin._lookup_shared_tone", return_value=None)

    from core.engine import SystemEngine
    return SystemEngine(settings={})


# ──────────────────────────────────────────────────────────────
# R-01..R-03 — make_timeline_entry
# ──────────────────────────────────────────────────────────────

class TestMakeTimelineEntry:

    def test_minor_key_keeps_scale_and_index(self):
        """R-01: 'Am' → nốt gốc A (index 9) + thể Minor. Mất chữ 'm' là gửi
        sang Studio One một tone TRƯỞNG dù bài là thứ."""
        entry = make_timeline_entry("Am")
        assert entry["key_display"] == "Am"
        assert entry["key_index"] == 9
        assert entry["scale"] == "Minor"
        assert entry["time"] == 0.0

    def test_sharp_major_key(self):
        """R-02: nốt thăng vẫn ra đúng index."""
        entry = make_timeline_entry("C#", at=12.5)
        assert (entry["key_index"], entry["scale"], entry["time"]) == (1, "Major", 12.5)

    @pytest.mark.parametrize("bad", ["", None, "Hm", "xyz"])
    def test_garbage_falls_back_to_c_major(self, bad):
        """R-03: tên tone rác → C Major, KHÔNG ném lỗi (không bao giờ chặn việc
        lưu dữ liệu người dùng)."""
        entry = make_timeline_entry(bad)
        assert entry == {"time": 0.0, "key_display": "C", "key_index": 0, "scale": "Major"}


# ──────────────────────────────────────────────────────────────
# R-04..R-07 — tone bài đã lưu vào được chuỗi resolve
# ──────────────────────────────────────────────────────────────

class TestSavedSongTone:

    def test_song_tone_becomes_timeline(self, isolated_data):
        """R-04: bài lưu tone 'Am' → dựng được timeline 1 mốc để replay."""
        _write_songs(isolated_data["songs"],
                     [{"id": 1, "title": "Bài A", "url": WATCH_URL, "tone": "Am"}])
        entry = song_tone_entry(WATCH_URL)
        assert entry is not None
        assert entry["origin"] == "song"
        assert entry["timeline"] == [make_timeline_entry("Am")]

    def test_matches_any_link_shape(self, isolated_data):
        """R-05: link chia sẻ / link có &list= vẫn phải khớp đúng bài đã lưu."""
        _write_songs(isolated_data["songs"],
                     [{"id": 1, "title": "Bài A", "url": WATCH_URL, "tone": "G"}])
        for url in (SHARE_URL, LIST_URL):
            assert song_tone_entry(url)["timeline"][0]["key_display"] == "G"

    def test_no_song_or_no_tone_returns_none(self, isolated_data):
        """R-06: không khớp bài / bài không có tone → None (dò tiếp như cũ)."""
        _write_songs(isolated_data["songs"],
                     [{"id": 1, "title": "Bài A", "url": WATCH_URL, "tone": ""}])
        assert song_tone_entry(WATCH_URL) is None
        assert song_tone_entry("https://www.youtube.com/watch?v=zzzzzzzzzzz") is None

    def test_manual_chain_beats_song_tone(self, isolated_data):
        """R-07: chuỗi tone thủ công (nhiều mốc) thắng tone đơn của bài."""
        _write_songs(isolated_data["songs"],
                     [{"id": 1, "title": "Bài A", "url": WATCH_URL, "tone": "G"}])
        chain = [make_timeline_entry("Am"), make_timeline_entry("C", at=60)]
        ManualToneTimeline.save_timeline(WATCH_URL, "Bài A", chain, source="human")
        assert saved_tone_timeline(WATCH_URL) == chain


# ──────────────────────────────────────────────────────────────
# R-08..R-09 — đệm resolve trong phiên
# ──────────────────────────────────────────────────────────────

class TestResolveCache:

    def test_song_tone_resolves_instead_of_detecting(self, engine, isolated_data):
        """R-08: bài chỉ có tone ở Danh sách bài hát → resolve ra 'manual',
        engine KHÔNG phải tải audio dò lại."""
        _write_songs(isolated_data["songs"],
                     [{"id": 1, "title": "Bài A", "url": WATCH_URL, "tone": "Am"}])
        source, data = engine._resolve_tone(SHARE_URL)
        assert source == "manual"
        assert data["origin"] == "song"
        assert data["timeline"][0]["key_display"] == "Am"

    def test_cache_keyed_by_video_id_not_raw_url(self, engine, isolated_data):
        """R-09a: cùng bài, khác dạng link → CÙNG một entry đệm phiên."""
        ToneCacheManager.save_tone(WATCH_URL, {
            "primary_key": "C",
            "key_timeline": [make_timeline_entry("C")],
        })
        assert engine._resolve_tone(WATCH_URL)[0] == "cache"
        assert list(engine._tone_resolve_cache.keys()) == [VIDEO_ID]
        # Link chia sẻ trúng luôn đệm phiên, không đọc lại đĩa.
        with patch.object(ToneCacheManager, "get_cached_tone") as disk:
            assert engine._resolve_tone(SHARE_URL)[0] == "cache"
            disk.assert_not_called()

    def test_manual_edit_invalidates_session_cache(self, engine, isolated_data):
        """R-09b: ĐIỂM MÙ CHÍNH — sửa chuỗi tone tay giữa phiên thì lần mở bài
        kế tiếp phải chạy tone MỚI, không phải tone tự động còn nằm trong RAM."""
        ToneCacheManager.save_tone(WATCH_URL, {
            "primary_key": "C",
            "key_timeline": [make_timeline_entry("C")],
        })
        assert engine._resolve_tone(WATCH_URL)[0] == "cache"   # nạp vào đệm phiên

        ManualToneTimeline.save_timeline(
            WATCH_URL, "Bài A", [make_timeline_entry("Am")], source="human")

        source, data = engine._resolve_tone(WATCH_URL)
        assert source == "manual"
        assert data["timeline"][0]["key_display"] == "Am"

    def test_data_version_bumps_on_writes(self, isolated_data):
        """R-09c: mọi đường ghi dữ liệu tone đều tăng thế hệ — không call site
        nào 'quên' báo cho đệm phiên được."""
        v0 = tone_cache.data_version()
        ToneCacheManager.save_tone(WATCH_URL, {"primary_key": "C", "key_timeline": []})
        v1 = tone_cache.data_version()
        ManualToneTimeline.save_timeline(WATCH_URL, "t", [make_timeline_entry("C")])
        v2 = tone_cache.data_version()
        ManualToneTimeline.delete_timeline(WATCH_URL)
        v3 = tone_cache.data_version()
        assert v0 < v1 < v2 < v3


# ──────────────────────────────────────────────────────────────
# R-10..R-12 — watcher so URL theo BÀI, không so chuỗi
# ──────────────────────────────────────────────────────────────

class TestEnsureToneForUrl:

    def test_dispatches_when_no_session(self, engine, mocker):
        """R-12a: mở bài mà chưa có phiên nào → phải kích dò tone. Từ khi watcher
        so URL theo bài, cú dò này không còn xảy ra 'nhờ may' nữa."""
        dispatch = mocker.patch.object(type(engine), "_dispatch_auto_detect")
        engine._ensure_tone_for_url(WATCH_URL)
        dispatch.assert_called_once()

    def test_skips_when_same_song_already_running(self, engine, mocker):
        """R-12b: đang replay/dò CHÍNH bài đó (dù link khác dạng) → để yên,
        không cắt ngang."""
        dispatch = mocker.patch.object(type(engine), "_dispatch_auto_detect")
        engine._tone_session.start_scanning(SHARE_URL)
        engine._ensure_tone_for_url(WATCH_URL)
        dispatch.assert_not_called()

    def test_dispatches_when_other_song_running(self, engine, mocker):
        """R-12c: phiên đang chạy là bài KHÁC → bài mới vẫn phải được dò."""
        dispatch = mocker.patch.object(type(engine), "_dispatch_auto_detect")
        engine._tone_session.start_scanning("https://www.youtube.com/watch?v=zzzzzzzzzzz")
        engine._ensure_tone_for_url(WATCH_URL)
        dispatch.assert_called_once()


class TestSameSong:

    def test_share_link_is_same_song_as_watch_link(self):
        """R-10: app mở youtu.be/…?si=… còn trình duyệt hiện youtube.com/watch?v=…
        → cùng bài, watcher KHÔNG được coi là bài mới rồi hủy replay để dò lại."""
        from core.engine._youtube import _same_song
        assert _same_song(SHARE_URL, WATCH_URL)
        assert _same_song(LIST_URL, WATCH_URL)

    def test_different_videos_are_not_same(self):
        """R-11: khác video → đúng là bài mới."""
        from core.engine._youtube import _same_song
        assert not _same_song(WATCH_URL, "https://www.youtube.com/watch?v=zzzzzzzzzzz")

    def test_missing_url_is_not_same(self):
        """R-12: chưa từng xem bài nào (None) → URL đầu tiên vẫn là bài mới."""
        from core.engine._youtube import _same_song
        assert not _same_song(WATCH_URL, None)
        assert not _same_song(None, None)


# ──────────────────────────────────────────────────────────────
# R-13..R-14 — chế độ "dò toàn bài" dùng chung chuỗi resolve
# ──────────────────────────────────────────────────────────────

class TestFullScanUsesResolveChain:

    def _no_download(self, mocker):
        """Bẫy: nếu luồng đi tới bước tải audio là test phải đỏ."""
        se = mocker.patch("core.engine._tone.ScoringEngine")
        se.return_value.download_youtube_audio.side_effect = AssertionError(
            "Không được tải audio khi tone đã có sẵn")
        return se

    def test_replays_cache_without_redetecting(self, engine, mocker, isolated_data):
        """R-13: có tone trong cache → chế độ full replay luôn, không tải + phân
        tích lại cả bài (trước đây chỉ chế độ nhanh mới biết dùng cache)."""
        self._no_download(mocker)
        mocker.patch("core.engine._tone._ToneMixin._send_tone_midi")
        engine._replay_cached_timeline = MagicMock()

        ToneCacheManager.save_tone(WATCH_URL, {
            "primary_key": "Am",
            "title": "Bài A",
            "key_timeline": [make_timeline_entry("Am")],
        })

        done = threading.Event()
        result = {}
        engine.auto_detect_youtube_timeline(
            WATCH_URL,
            on_complete=lambda r: (result.update(r), done.set()),
            on_error=MagicMock(),
        )
        assert done.wait(timeout=5)
        assert result["from_cache"] is True
        assert result["timeline"][0]["key_display"] == "Am"
        engine._replay_cached_timeline.assert_called_once()

    def test_force_rescan_still_bypasses_saved_tone(self, engine, mocker, isolated_data):
        """R-14: bấm "Dò Lại" (skip_resolve=True) vẫn phải dò mới — nếu không thì
        tone sai sẽ khóa cứng bài, không sửa được."""
        se = mocker.patch("core.engine._tone.ScoringEngine")
        se.return_value.download_youtube_audio.return_value = None   # dừng sớm
        mocker.patch("core.engine._tone._ToneMixin._loopback_fallback_detect",
                     return_value=None)
        mocker.patch("core.engine._tone.extract_info_with_auth", return_value={"title": "t"})
        mocker.patch("core.engine._tone.make_ydl_opts", return_value={})
        resolve = mocker.patch("core.engine._tone._ToneMixin._resolve_tone")

        ManualToneTimeline.save_timeline(
            WATCH_URL, "Bài A", [make_timeline_entry("Am")], source="human")

        done = threading.Event()
        engine.auto_detect_youtube_timeline(
            WATCH_URL,
            on_complete=MagicMock(side_effect=lambda r: done.set()),
            on_error=MagicMock(side_effect=lambda m: done.set()),
            skip_resolve=True,
        )
        assert done.wait(timeout=5)
        resolve.assert_not_called()
