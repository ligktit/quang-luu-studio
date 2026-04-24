import pytest
import json
import time
from unittest.mock import patch
from core.tone_cache import ToneCacheManager, ManualToneTimeline

@pytest.fixture(autouse=True)
def mock_cache_files(tmp_path):
    tone_file = tmp_path / "tone_cache.json"
    timeline_file = tmp_path / "manual_timelines.json"
    
    with patch("core.tone_cache.ToneCacheManager.CACHE_FILE", str(tone_file)), \
         patch("core.tone_cache.MANUAL_TIMELINES_FILE", str(timeline_file)):
        yield (tone_file, timeline_file)

# --- 8.1 ToneCacheManager ---

def test_get_cached_tone_empty():
    # TC-01
    assert ToneCacheManager.get_cached_tone("https://www.youtube.com/watch?v=12345678901") is None

def test_get_cached_tone_valid():
    # TC-02
    tone_data = {"key_idx": 0, "scale": "Major", "tone": "C Major"}
    ToneCacheManager.save_tone("https://www.youtube.com/watch?v=12345678901", tone_data)
    res = ToneCacheManager.get_cached_tone("https://www.youtube.com/watch?v=12345678901")
    assert res is not None
    assert res["tone"] == "C Major"

def test_get_cached_tone_expired(mock_cache_files):
    # TC-03
    tone_file, _ = mock_cache_files
    data = {"12345678901": {"tone": "C Major", "cached_at": time.time() - (31 * 86400)}}
    tone_file.write_text(json.dumps(data), encoding="utf-8")
    assert ToneCacheManager.get_cached_tone("https://www.youtube.com/watch?v=12345678901") is None

def test_save_tone(mock_cache_files):
    # TC-04
    tone_file, _ = mock_cache_files
    ToneCacheManager.save_tone("https://www.youtube.com/watch?v=12345678901", {"tone": "D Major"})
    data = json.loads(tone_file.read_text(encoding="utf-8"))
    assert "12345678901" in data
    assert data["12345678901"]["tone"] == "D Major"

def test_save_and_get_round_trip():
    # TC-05
    ToneCacheManager.save_tone("https://www.youtube.com/watch?v=12345678901", {"tone": "E Minor"})
    res = ToneCacheManager.get_cached_tone("https://www.youtube.com/watch?v=12345678901")
    assert res["tone"] == "E Minor"

def test_clear_cache(mock_cache_files):
    # TC-06
    tone_file, _ = mock_cache_files
    data = {"11111111111": {}, "22222222222": {}, "33333333333": {}}
    tone_file.write_text(json.dumps(data), encoding="utf-8")
    ToneCacheManager.clear_cache()
    cleared = json.loads(tone_file.read_text(encoding="utf-8"))
    assert cleared == {}

def test_url_with_params_stripped():
    # TC-07
    ToneCacheManager.save_tone("https://www.youtube.com/watch?v=12345678901&list=abc", {"tone": "F Major"})
    res = ToneCacheManager.get_cached_tone("https://www.youtube.com/watch?v=12345678901?t=42")
    assert res is not None
    assert res["tone"] == "F Major"

# --- 8.2 ManualToneTimeline ---

def test_time_str_to_seconds():
    # TC-08, TC-09
    assert ManualToneTimeline.time_str_to_seconds("01:30") == 90
    assert ManualToneTimeline.time_str_to_seconds("00:05") == 5

def test_seconds_to_time_str():
    # TC-10, TC-11
    assert ManualToneTimeline.seconds_to_time_str(90) == "1:30"
    # Actually the function might return "61:01", let's check format
    assert ManualToneTimeline.seconds_to_time_str(3661) == "61:01"

def test_get_entry_at_position():
    # TC-12, TC-13
    timeline = [
        {"time": 0, "tone": "C"},
        {"time": 30, "tone": "D"},
        {"time": 60, "tone": "G"}
    ]
    entry, idx = ManualToneTimeline.get_entry_at_position(timeline, 45)
    assert idx == 1
    assert entry["tone"] == "D"
    
    entry0, idx0 = ManualToneTimeline.get_entry_at_position(timeline, 0)
    assert idx0 == 0
    assert entry0["tone"] == "C"

def test_save_load_timeline_round_trip():
    # TC-14
    entries = [{"time": 0, "tone": "C"}]
    ManualToneTimeline.save_timeline("https://www.youtube.com/watch?v=12345678901", "Test", entries)
    res = ManualToneTimeline.load_timeline("https://www.youtube.com/watch?v=12345678901")
    assert res is not None
    assert res["title"] == "Test"
    assert res["timeline"] == entries

def test_delete_timeline():
    # TC-15
    ManualToneTimeline.save_timeline("https://www.youtube.com/watch?v=12345678901", "Test", [])
    ManualToneTimeline.delete_timeline("https://www.youtube.com/watch?v=12345678901")
    assert ManualToneTimeline.load_timeline("https://www.youtube.com/watch?v=12345678901") is None

def test_list_all_timelines():
    # TC-16
    ManualToneTimeline.save_timeline("https://www.youtube.com/watch?v=11111111111", "T1", [])
    ManualToneTimeline.save_timeline("https://www.youtube.com/watch?v=22222222222", "T2", [])
    all_tl = ManualToneTimeline.list_all_timelines()
    assert len(all_tl) == 2
    titles = [t["title"] for t in all_tl]
    assert "T1" in titles and "T2" in titles
