"""
Test core/score_history.py — không cần Qt (chỉ test lớp data).

Chạy: python -m pytest tests/test_score_history.py -q
"""
import os
import json

import pytest

from core import score_history
from core.score_history import ScoreHistory, MAX_ENTRIES


@pytest.fixture
def hist_file(tmp_path, monkeypatch):
    """Trỏ HISTORY_FILE sang file tạm để không đụng dữ liệu thật."""
    f = tmp_path / "score_history.json"
    monkeypatch.setattr(score_history, "HISTORY_FILE", str(f))
    return str(f)


def _report(total=80, intonation=70, stability=90, rhythm=60, key=50):
    return {
        "total_score": total,
        "pitch_intonation": intonation,
        "pitch_stability": stability,
        "volume_consistency": 88,
        "rhythm_score": rhythm,
        "key_conformity": key,
        "voiced_ratio": 95,
        "feedback": {"rank": "Ca Si", "icon": "🎤", "main": "ok", "tips": []},
    }


def test_empty_load_and_summary(hist_file):
    assert ScoreHistory.load() == []
    s = ScoreHistory.summary()
    assert s["count"] == 0
    assert s["avg_overall"] == 0.0
    assert s["trend"] == "flat"


def test_add_and_load(hist_file):
    assert ScoreHistory.add(_report(80), song_title="Bài A", url="http://x/1") is True
    hist = ScoreHistory.load()
    assert len(hist) == 1
    e = hist[0]
    assert e["song_title"] == "Bài A"
    assert e["url"] == "http://x/1"
    assert e["overall"] == 80
    # pitch = TB của intonation (70) và stability (90) = 80
    assert e["pitch"] == 80.0
    assert e["rhythm"] == 60
    assert e["tone"] == 50
    assert "timestamp" in e


def test_pitch_uses_nonzero_only(hist_file):
    # Nhánh scoring chỉ có stability (intonation = 0) → pitch = stability
    ScoreHistory.add(_report(75, intonation=0, stability=88))
    e = ScoreHistory.load()[0]
    assert e["pitch"] == 88.0


def test_summary_stats(hist_file):
    for total in (60, 70, 80):
        ScoreHistory.add(_report(total))
    s = ScoreHistory.summary()
    assert s["count"] == 3
    assert s["avg_overall"] == 70.0
    assert s["best"] == 80.0
    assert s["latest"] == 80.0


def test_summary_trend_up(hist_file):
    # 4 điểm thấp rồi 4 điểm cao → xu hướng tăng
    for total in (50, 52, 51, 53, 80, 82, 81, 83):
        ScoreHistory.add(_report(total))
    s = ScoreHistory.summary()
    assert s["trend"] == "up"
    assert s["trend_delta"] > 0


def test_summary_trend_down(hist_file):
    for total in (85, 86, 84, 87, 55, 54, 56, 53):
        ScoreHistory.add(_report(total))
    s = ScoreHistory.summary()
    assert s["trend"] == "down"
    assert s["trend_delta"] < 0


def test_recent(hist_file):
    for total in range(1, 11):
        ScoreHistory.add(_report(total))
    r = ScoreHistory.recent(3)
    assert len(r) == 3
    assert [e["overall"] for e in r] == [8, 9, 10]
    assert ScoreHistory.recent(0) == []


def test_cap_max_entries(hist_file):
    for i in range(MAX_ENTRIES + 25):
        ScoreHistory.add(_report(i % 100))
    hist = ScoreHistory.load()
    assert len(hist) == MAX_ENTRIES
    # Phải giữ entry MỚI NHẤT (cuối), cắt entry cũ nhất
    last = ScoreHistory.recent(1)[0]
    assert last["overall"] == (MAX_ENTRIES + 24) % 100


def test_fail_soft_corrupt_file(hist_file):
    with open(hist_file, "w", encoding="utf-8") as f:
        f.write("{ this is not valid json ]")
    # load không vỡ → []
    assert ScoreHistory.load() == []
    # summary cũng fail-soft
    assert ScoreHistory.summary()["count"] == 0


def test_fail_soft_non_list(hist_file):
    with open(hist_file, "w", encoding="utf-8") as f:
        json.dump({"not": "a list"}, f)
    assert ScoreHistory.load() == []


def test_add_overwrites_then_appends(hist_file):
    ScoreHistory.add(_report(80))
    ScoreHistory.add(_report(90))
    hist = ScoreHistory.load()
    assert len(hist) == 2
    assert [e["overall"] for e in hist] == [80, 90]
    # File trên đĩa hợp lệ
    with open(hist_file, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    assert isinstance(on_disk, list) and len(on_disk) == 2
