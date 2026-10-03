"""tonelib: nguồn admin, đọc mốc thời gian từ form, cursor keyset."""
from datetime import datetime, timezone

from app.services import tonelib


def test_nguon_admin_nang_hon_nguoi_sua():
    assert "admin" in tonelib.SOURCES
    assert tonelib.SOURCE_WEIGHT["admin"] > tonelib.SOURCE_WEIGHT["human"]
    assert tonelib.CLIENT_SOURCES == ("auto", "human")


def test_key_display_tu_index_va_the():
    assert tonelib.key_display(6, "Minor") == "F#m"
    assert tonelib.key_display(0, "Major") == "C"
    assert tonelib.key_display(11, "Minor") == "Bm"


def test_parse_time_cac_dang():
    assert tonelib.parse_time("1:35") == 95.0
    assert tonelib.parse_time("95") == 95.0
    assert tonelib.parse_time("1:02:03") == 3723.0
    assert tonelib.parse_time("0:00") == 0.0
    assert tonelib.parse_time("abc") is None
    assert tonelib.parse_time("1:xx") is None
    assert tonelib.parse_time("-5") is None


def test_parse_timeline_text_trong_thi_mot_moc_theo_tone_chinh():
    entries = tonelib.parse_timeline_text("", "F#m")
    assert entries == [{"time": 0.0, "key_display": "F#m", "key_index": 6, "scale": "Minor"}]


def test_parse_timeline_text_nhieu_moc_sap_theo_thoi_gian():
    entries = tonelib.parse_timeline_text("1:35 Bm\n0:00 F#m\n\n3:10 C# Major", "F#m")
    assert [e["time"] for e in entries] == [0.0, 95.0, 190.0]
    assert [e["key_display"] for e in entries] == ["F#m", "Bm", "C#"]
    assert entries[2] == {"time": 190.0, "key_display": "C#", "key_index": 1, "scale": "Major"}


def test_parse_timeline_text_dong_hong_thi_tra_none():
    assert tonelib.parse_timeline_text("0:00 F#m\n1:35", "F#m") is None
    assert tonelib.parse_timeline_text("0:00 Xm", "F#m") is None
    assert tonelib.parse_timeline_text("", "không phải tone") is None


def test_cursor_di_va_ve_giu_nguyen_micro_giay():
    ts = datetime(2026, 10, 3, 10, 0, 0, 123456, tzinfo=timezone.utc)
    text = tonelib.encode_cursor(ts, 42)
    assert isinstance(text, str) and "=" not in text and "{" not in text
    assert tonelib.decode_cursor(text) == (ts, 42)


def test_cursor_hong_tra_none():
    assert tonelib.decode_cursor("") is None
    assert tonelib.decode_cursor("không phải base64!!") is None
    assert tonelib.decode_cursor(tonelib._b64(b'{"ts": 5, "id": "x"}')) is None
    assert tonelib.decode_cursor(tonelib._b64(b'[1,2]')) is None
