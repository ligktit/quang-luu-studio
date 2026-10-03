"""
Tests Phase 2 — Smart Recall: core.presets (thuần) + SongManager.save/get_preset.

Chạy: python -m pytest tests/test_presets.py -q   (KHÔNG cần Qt).
"""
import pytest
from unittest.mock import patch

from core import presets
from core.songs import SongManager


# ── Fixture: SongManager dùng file tạm (theo pattern tests/core/test_songs.py) ──
@pytest.fixture(autouse=True)
def mock_songs_file(tmp_path):
    songs_file = tmp_path / "saved_songs.json"
    playlists_file = tmp_path / "playlists.json"
    with patch("core.songs.SONGS_FILE", str(songs_file)), \
         patch("core.songs.PLAYLISTS_FILE", str(playlists_file)):
        yield songs_file


# ── core.presets.normalize_preset ──────────────────────────────────────────

def test_normalize_full_preset():
    raw = {
        "tone": "Am",
        "scale": "Minor",
        "mixer": {"music": 70, "mic": 5, "reverb": -3, "backing": 50},
        "mode": "Lofi",
    }
    p = presets.normalize_preset(raw)
    assert p["tone"] == "Am"
    assert p["scale"] == "Minor"
    assert p["modes"] == ["Lofi"]
    assert p["mode"] == "Lofi"
    assert p["mixer"] == {"music": 70, "mic": 5, "reverb": -3, "backing": 50}


def test_normalize_missing_fields_default_none():
    p = presets.normalize_preset({})
    assert p == presets.empty_preset()
    assert p == {"tone": None, "scale": None, "tone_locked": None,
                 "tone_music": None, "tone_voice": None,
                 "mixer": {}, "modes": [], "mode": None, "toggles": {}}


def test_normalize_always_has_all_keys():
    for raw in (None, {}, [], "abc", 123, {"tone": "C"}):
        p = presets.normalize_preset(raw)
        assert set(p.keys()) == set(presets.empty_preset())


def test_normalize_keeps_multiple_modes():
    # Các nút MODE là toggle độc lập → bật Lofi + Remix cùng lúc phải lưu được cả hai.
    p = presets.normalize_preset({"modes": ["Lofi", "Remix"]})
    assert p["modes"] == ["Lofi", "Remix"]
    # "mode" chỉ là mirror cho bản cũ đọc
    assert p["mode"] == "Lofi"


def test_normalize_modes_legacy_single_mode_and_cleanup():
    # Preset đời cũ (thời nhóm radio) chỉ có khóa "mode"
    assert presets.normalize_preset({"mode": "Remix"})["modes"] == ["Remix"]
    # "modes" có thì thắng "mode"; rác/trùng bị loại, giữ thứ tự
    p = presets.normalize_preset(
        {"mode": "Lofi", "modes": [" Remix ", "", None, 7, "Remix", "Dân Ca"]})
    assert p["modes"] == ["Remix", "Dân Ca"]


def test_normalize_invalid_scale_dropped():
    assert presets.normalize_preset({"scale": "Lydian"})["scale"] is None
    assert presets.normalize_preset({"scale": ""})["scale"] is None
    assert presets.normalize_preset({"scale": "Major"})["scale"] == "Major"


def test_normalize_tone_and_mode_strip_and_blank():
    p = presets.normalize_preset({"tone": "  F#m  ", "mode": "  Remix "})
    assert p["tone"] == "F#m"
    assert p["mode"] == "Remix"
    assert presets.normalize_preset({"tone": "   ", "mode": ""}) == presets.empty_preset()


def test_normalize_mixer_partial_and_coercion():
    # field thiếu bị bỏ qua; string số ép được; giá trị hỏng bị loại
    raw = {"mixer": {"music": "70", "mic": 3.6, "reverb": "x", "backing": None}}
    mx = presets.normalize_preset(raw)["mixer"]
    assert mx == {"music": 70, "mic": 4}  # reverb/backing bị loại; 3.6 -> 4


def test_normalize_mixer_bool_rejected():
    # bool không bị nhận nhầm thành 1/0
    mx = presets.normalize_preset({"mixer": {"music": True}})["mixer"]
    assert mx == {}


def test_is_empty_preset():
    assert presets.is_empty_preset(None) is True
    assert presets.is_empty_preset({}) is True
    assert presets.is_empty_preset({"mixer": {}}) is True
    assert presets.is_empty_preset({"tone": "C"}) is False
    assert presets.is_empty_preset({"mixer": {"music": 1}}) is False


def test_merge_preset_does_not_mutate_song():
    song = {"id": 1, "title": "A", "tone": "C"}
    merged = presets.merge_preset(song, {"tone": "Am", "scale": "Minor"})
    assert "preset" not in song  # gốc không bị đụng
    assert merged["preset"]["tone"] == "Am"
    assert merged["title"] == "A"


# ── SongManager.save_preset / get_preset ───────────────────────────────────

def test_get_preset_none_when_song_missing():
    assert SongManager.get_preset(999) is None


def test_get_preset_none_when_no_preset_field():
    # Bài cũ chưa có preset → None (tương thích ngược)
    SongManager.add_song("Song", "http://yt.com/1", "C")
    assert SongManager.get_preset(1) is None


def test_save_and_get_preset_round_trip():
    SongManager.add_song("Song", "http://yt.com/1", "C")
    ok = SongManager.save_preset(1, {
        "tone": "G", "scale": "Major",
        "mixer": {"music": 80, "mic": 2}, "mode": "Remix",
    })
    assert ok is True
    p = SongManager.get_preset(1)
    assert p["tone"] == "G"
    assert p["scale"] == "Major"
    assert p["mixer"] == {"music": 80, "mic": 2}
    assert p["mode"] == "Remix"


def test_save_preset_normalizes_garbage():
    SongManager.add_song("Song", "http://yt.com/1", "C")
    SongManager.save_preset(1, {"tone": "  Am ", "scale": "bogus", "mixer": {"mic": "9"}})
    p = SongManager.get_preset(1)
    assert p["tone"] == "Am"
    assert p["scale"] is None
    assert p["mixer"] == {"mic": 9}


def test_save_preset_returns_false_for_unknown_id():
    assert SongManager.save_preset(123, {"tone": "C"}) is False


def test_add_song_with_preset():
    SongManager.add_song("Song", "http://yt.com/1", "C",
                         preset={"tone": "Dm", "mode": "Dân Ca"})
    p = SongManager.get_preset(1)
    assert p["tone"] == "Dm"
    assert p["mode"] == "Dân Ca"


def test_add_song_without_preset_stays_backward_compatible():
    # Không truyền preset → bài không có khóa preset, get_preset = None
    SongManager.add_song("Song", "http://yt.com/1", "C")
    song = SongManager.get_song_by_id(1)
    assert "preset" not in song
    assert SongManager.get_preset(1) is None


def test_add_song_update_preserves_existing_preset_when_none():
    # Lưu preset, rồi add_song lại (update path) không truyền preset → giữ nguyên
    SongManager.add_song("Song", "http://yt.com/1", "C")
    SongManager.save_preset(1, {"tone": "Em"})
    SongManager.add_song("Song renamed", "http://yt.com/1", "D")  # update path
    assert SongManager.get_preset(1)["tone"] == "Em"


def test_update_song_with_preset_normalizes():
    SongManager.add_song("Song", "http://yt.com/1", "C")
    SongManager.update_song(1, preset={"scale": "Minor", "mixer": {"reverb": -2}})
    p = SongManager.get_preset(1)
    assert p["scale"] == "Minor"
    assert p["mixer"] == {"reverb": -2}


# ── Schema v2: thiết lập theo bài (Tone Nhạc/Giọng, tone chốt tay, nút bật/tắt) ──

def test_normalize_tone_offsets_clamped_and_coerced():
    p = presets.normalize_preset({"tone_music": 3, "tone_voice": "-2"})
    assert (p["tone_music"], p["tone_voice"]) == (3, -2)
    p = presets.normalize_preset({"tone_music": 40, "tone_voice": -99})
    assert (p["tone_music"], p["tone_voice"]) == (12, -12)
    p = presets.normalize_preset({"tone_music": "x", "tone_voice": True})
    assert (p["tone_music"], p["tone_voice"]) == (None, None)


def test_normalize_tone_locked_only_bool():
    assert presets.normalize_preset({"tone_locked": True})["tone_locked"] is True
    assert presets.normalize_preset({"tone_locked": False})["tone_locked"] is False
    assert presets.normalize_preset({"tone_locked": 1})["tone_locked"] is None


def test_normalize_toggles_only_bool_values():
    t = presets.normalize_preset(
        {"toggles": {"be": True, "fix_meo": False, "tat_on": 1, "": True}})["toggles"]
    assert t == {"be": True, "fix_meo": False}


def test_normalize_mixer_keeps_custom_channels():
    # Kênh tự thêm ở Dev Mode lưu bằng cc_key của nó.
    mx = presets.normalize_preset({"mixer": {"music": 70, "60": 12, "": 5}})["mixer"]
    assert mx == {"music": 70, "60": 12}


def test_normalize_keeps_unknown_settings_for_future_versions():
    # Thiết lập của bản app mới hơn không được rơi mất khi bản cũ lưu lại.
    raw = {"tone": "C", "v": 2, "eq_preset": {"name": "Warm", "gain": [1, 2]},
           "bad": object()}
    p = presets.normalize_preset(raw)
    assert p["v"] == 2
    assert p["eq_preset"] == {"name": "Warm", "gain": [1, 2]}
    assert "bad" not in p


def test_is_empty_preset_sees_new_fields():
    assert presets.is_empty_preset({"tone_voice": 0}) is False
    assert presets.is_empty_preset({"toggles": {"be": True}}) is False
    assert presets.is_empty_preset({"v": 2}) is False


def test_find_song_by_url_matches_video_id():
    SongManager.add_song("Bài A", "https://www.youtube.com/watch?v=abcdefghijk", "Am",
                         preset={"tone_music": 2})
    song = SongManager.find_song_by_url("https://youtu.be/abcdefghijk?si=xyz")
    assert song is not None and song["title"] == "Bài A"
    assert SongManager.find_song_by_url("https://www.youtube.com/watch?v=zzzzzzzzzzz") is None
    assert SongManager.find_song_by_url("") is None
