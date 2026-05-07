"""Tests cho core.accessibility package."""
import pytest

from core.accessibility.voice_input import match_intent, Intent
from core.accessibility.announcer import key_to_vn
from core.accessibility.theme import ThemeManager


# ── Voice intent matcher ──────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("dò tone bài này đi", "autokey"),
    ("tu dong do tone", "autokey"),
    ("ghi âm nào", "record_toggle"),
    ("lưu bài này lại", "save"),
    ("mở danh sách bài", "open_songs"),
    ("chấm điểm cho tôi", "score"),
    ("đọc trạng thái", "speak_status"),
    ("tắt giọng đi", "stop_tts"),
    ("tắt nhạc", "mute_music"),
    ("tắt mic", "mute_mic"),
    ("tăng nhạc lên chút", "volume_up_music"),
    ("giảm nhạc đi", "volume_down_music"),
    ("tăng mic", "volume_up_mic"),
    ("thêm vang", "volume_up_reverb"),
    ("chế độ remix", "mode_remix"),
    ("đa thể loại", "mode_datheloai"),
])
def test_match_intent_recognizes_known_phrases(text, expected):
    intent = match_intent(text)
    assert intent is not None, f"không match được: {text!r}"
    assert intent.name == expected
    assert intent.text == text


def test_match_intent_returns_none_for_unknown():
    assert match_intent("xin chào") is None
    assert match_intent("") is None
    assert match_intent("12345") is None


# ── key_to_vn ─────────────────────────────────────────────────

@pytest.mark.parametrize("key,scale,expected", [
    ("C", "Major", "Đô trưởng"),
    ("A", "Minor", "La thứ"),
    ("F#", "Major", "Fa thăng trưởng"),
    ("Bb", "", "Si giáng"),
    ("D", "", "Rê"),
])
def test_key_to_vn(key, scale, expected):
    assert key_to_vn(key, scale) == expected


# ── ThemeManager ──────────────────────────────────────────────

def test_theme_font_scale_clamping():
    tm = ThemeManager()
    tm.set_font_scale(5.0)
    assert tm.font_scale() == ThemeManager.MAX_SCALE
    tm.set_font_scale(0.1)
    assert tm.font_scale() == ThemeManager.MIN_SCALE


def test_theme_increase_decrease():
    tm = ThemeManager()
    base = tm.font_scale()
    tm.increase_font()
    assert tm.font_scale() == round(base + ThemeManager.STEP, 2)
    tm.decrease_font()
    tm.decrease_font()
    assert tm.font_scale() == round(base - ThemeManager.STEP, 2)


def test_theme_high_contrast_toggle():
    tm = ThemeManager()
    assert tm.is_high_contrast() is False
    tm.set_high_contrast(True)
    assert tm.is_high_contrast() is True


# ── AppConfig.set_accessibility ───────────────────────────────

def test_app_config_accessibility_round_trip(tmp_path, monkeypatch):
    # Tạo AppConfig isolated bằng cách override path
    from core import config as cfg_mod
    monkeypatch.setattr(cfg_mod.AppConfig, "_data", None)
    monkeypatch.setattr(cfg_mod, "APP_DIR", str(tmp_path))
    # Force reload với defaults
    cfg_mod.AppConfig.reload()
    cfg = cfg_mod.AppConfig.get_accessibility()
    assert "tts_enabled" in cfg
    assert cfg["tts_enabled"] is False

    cfg_mod.AppConfig.set_accessibility(tts_enabled=True, font_scale=1.5)
    cfg2 = cfg_mod.AppConfig.get_accessibility()
    assert cfg2["tts_enabled"] is True
    assert cfg2["font_scale"] == 1.5
