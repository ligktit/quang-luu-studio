"""
Test core/engine/_setlist.py — SetlistController (Phase 5 Live Setlist).

Chỉ test CONTROLLER thuần (không import dialog / Qt). Dùng ToneCacheManager tạm
(monkeypatch CACHE_FILE) + detect_fn giả lập.

Chạy: python -m pytest tests/test_setlist.py -q
"""
import threading

import pytest

from core.engine._setlist import SetlistController, tone_already_cached
from core import tone_cache
from core.tone_cache import ToneCacheManager


@pytest.fixture
def temp_cache(tmp_path, monkeypatch):
    """Trỏ tone cache + manual timeline sang file tạm."""
    cache_f = tmp_path / "tone_cache.json"
    manual_f = tmp_path / "manual_timelines.json"
    monkeypatch.setattr(ToneCacheManager, "CACHE_FILE", str(cache_f))
    monkeypatch.setattr(tone_cache, "MANUAL_TIMELINES_FILE", str(manual_f))
    return str(cache_f)


def _songs(*urls):
    return [{"id": i, "title": f"Bài {i}", "url": u, "tone": "C"} for i, u in enumerate(urls)]


# ── Con trỏ advance/peek/current ─────────────────────────────────────────────

def test_advance_and_peek():
    ctrl = SetlistController(_songs("u0", "u1", "u2"))
    assert len(ctrl) == 3
    assert ctrl.current() is None          # chưa bắt đầu
    assert ctrl.peek_next()["url"] == "u0"

    first = ctrl.advance()
    assert first["url"] == "u0"
    assert ctrl.current()["url"] == "u0"
    assert ctrl.peek_next()["url"] == "u1"
    assert ctrl.has_next() is True

    assert ctrl.advance()["url"] == "u1"
    assert ctrl.advance()["url"] == "u2"
    assert ctrl.has_next() is False
    assert ctrl.advance() is None          # hết
    assert ctrl.peek_next() is None


def test_empty_setlist():
    ctrl = SetlistController([])
    assert len(ctrl) == 0
    assert ctrl.advance() is None
    assert ctrl.current() is None
    assert ctrl.peek_next() is None
    assert ctrl.prefetch_next(lambda url, on_done=None: None) is False


def test_reset_and_set_songs():
    ctrl = SetlistController(_songs("a", "b"))
    ctrl.advance()
    ctrl.advance()
    ctrl.reset()
    assert ctrl.current() is None
    assert ctrl.advance()["url"] == "a"

    ctrl.set_songs(_songs("x"))
    assert ctrl.current() is None
    assert ctrl.advance()["url"] == "x"


# ── tone_already_cached / prefetch ───────────────────────────────────────────

def test_tone_already_cached(temp_cache):
    assert tone_already_cached("https://yt/CACHED") is False
    ToneCacheManager.save_tone("https://yt/CACHED", {
        "primary_key": "G",
        "key_timeline": [{"time": 0, "key_display": "G", "key_index": 7, "scale": "Major"}],
    })
    assert tone_already_cached("https://yt/CACHED") is True
    assert tone_already_cached("") is False


def test_prefetch_calls_detect_for_uncached(temp_cache):
    ctrl = SetlistController(_songs("u0", "u1"))
    ctrl.advance()  # current=u0, next=u1

    called = []
    done_evt = threading.Event()

    def detect_fn(url, on_done=None):
        called.append(url)
        # Giả lập engine ghi cache rồi báo xong.
        ToneCacheManager.save_tone(url, {
            "primary_key": "A",
            "key_timeline": [{"time": 0, "key_display": "A", "key_index": 9, "scale": "Minor"}],
        })
        if on_done:
            on_done({"ok": True})

    finished = []
    ctrl.prefetch_next(detect_fn, on_done=lambda url, cached: (finished.append((url, cached)), done_evt.set()))
    assert done_evt.wait(timeout=5.0)
    assert called == ["u1"]
    assert finished[0] == ("u1", False)
    assert tone_already_cached("u1") is True


def test_prefetch_skips_cached(temp_cache):
    # Bài kế đã có tone → detect_fn KHÔNG được gọi.
    ToneCacheManager.save_tone("u1", {
        "primary_key": "C",
        "key_timeline": [{"time": 0, "key_display": "C", "key_index": 0, "scale": "Major"}],
    })
    ctrl = SetlistController(_songs("u0", "u1"))
    ctrl.advance()

    called = []
    done = []
    ok = ctrl.prefetch_next(
        lambda url, on_done=None: called.append(url),
        on_done=lambda url, cached: done.append((url, cached)),
    )
    assert ok is True
    assert called == []                 # bỏ qua dò
    assert done == [("u1", True)]       # báo đã cache sẵn


def test_prefetch_no_next(temp_cache):
    ctrl = SetlistController(_songs("only"))
    ctrl.advance()                      # current=only, không còn bài kế
    assert ctrl.prefetch_next(lambda url, on_done=None: None) is False


def test_prefetch_detect_fn_without_on_done(temp_cache):
    """detect_fn chỉ nhận (url) — controller vẫn xử lý qua nhánh TypeError."""
    ctrl = SetlistController(_songs("u0", "u1"))
    ctrl.advance()
    called = []
    done_evt = threading.Event()

    def detect_fn(url):
        called.append(url)

    ctrl.prefetch_next(detect_fn, on_done=lambda url, cached: done_evt.set())
    assert done_evt.wait(timeout=5.0)
    assert called == ["u1"]


def test_prefetch_failsoft(temp_cache):
    """detect_fn ném lỗi → prefetch nuốt, vẫn gọi on_done, không vỡ."""
    ctrl = SetlistController(_songs("u0", "u1"))
    ctrl.advance()
    done_evt = threading.Event()

    def detect_fn(url, on_done=None):
        raise RuntimeError("boom")

    ctrl.prefetch_next(detect_fn, on_done=lambda url, cached: done_evt.set())
    assert done_evt.wait(timeout=5.0)
