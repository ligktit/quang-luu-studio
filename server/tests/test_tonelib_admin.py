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


def test_parse_time_khong_nhan_inf_nan_hay_so_mu():
    """'inf' làm normalize_timeline ném OverflowError (500 trên form); 'nan' đi
    vào timeline ghim và phát tới mọi máy. Chỉ nhận chữ số (và một dấu chấm)."""
    for text in ("inf", "nan", "1e3", "-inf", "1:nan", "0x10"):
        assert tonelib.parse_time(text) is None, text
    assert tonelib.parse_time("1.5") == 1.5
    assert tonelib.parse_time("2:30.5") == 150.5


def test_decode_cursor_ts_naive_duoc_ep_ve_utc():
    """Server luôn phát aware; ai sửa tay file trạng thái gửi naive thì Postgres
    cast theo TimeZone phiên → lệch giờ. Ép UTC để so cùng một mốc."""
    text = tonelib._b64(b'{"ts": "2026-10-03T10:00:00.123456", "id": 7}')
    ts, tone_id = tonelib.decode_cursor(text)
    assert tone_id == 7
    assert ts.tzinfo is not None and ts.utcoffset().total_seconds() == 0
    assert ts == datetime(2026, 10, 3, 10, 0, 0, 123456, tzinfo=timezone.utc)


def test_parse_timeline_text_mot_dong_phan_cach_bang_dau_phay():
    entries = tonelib.parse_timeline_text("0:00 Gm, 3:57 G#m; 4:30 Am", "")
    assert [(e["time"], e["key_display"]) for e in entries] == [(0.0, "Gm"), (237.0, "G#m"), (270.0, "Am")]


def test_parse_timeline_text_moc_dau_khong_phai_0_thi_chen_tone_chinh():
    entries = tonelib.parse_timeline_text("3:57 G#m", "Gm")
    assert [(e["time"], e["key_display"]) for e in entries] == [(0.0, "Gm"), (237.0, "G#m")]
    # Không có tone chính thì không biết trước 3:57 hát tone gì → từ chối.
    assert tonelib.parse_timeline_text("3:57 G#m", "") is None


def test_parse_timeline_text_trung_moc_thi_tra_none():
    assert tonelib.parse_timeline_text("0:00 Gm\n3:57 G#m\n3:57 Am", "Gm") is None


def test_parse_timeline_text_gop_moc_lien_tiep_cung_tone():
    entries = tonelib.parse_timeline_text("0:00 Gm\n1:00 Gm\n3:57 G#m", "")
    assert [(e["time"], e["key_display"]) for e in entries] == [(0.0, "Gm"), (237.0, "G#m")]


def test_parse_timeline_text_qua_tran_moc_thi_tra_none():
    text = "\n".join(f"{i} {'Gm' if i % 2 else 'Am'}" for i in range(tonelib.MAX_ENTRIES + 1))
    assert tonelib.parse_timeline_text(text, "Am") is None


def test_format_timeline_doc_lai_duoc():
    entries = [{"time": 0.0, "key_display": "Gm"}, {"time": 237.0, "key_display": "G#m"},
               {"time": 254.5, "key_display": "C#"}, {"time": 3723.0, "key_display": "D"}]
    text = tonelib.format_timeline(entries)
    assert text == "0:00 Gm\n3:57 G#m\n4:14.5 C#\n1:02:03 D"
    again = tonelib.parse_timeline_text(text, "")
    assert [(e["time"], e["key_display"]) for e in again] == [(e["time"], e["key_display"]) for e in entries]
    assert tonelib.format_timeline("không phải list") == ""


def test_timeline_steps_co_gio_va_so_nua_cung():
    entries = [{"time": 0.0, "key_display": "Gm"}, {"time": 237.0, "key_display": "G#m"},
               {"time": 289.0, "key_display": "Fm"}, {"time": 300.0, "key_display": "F"}]
    assert tonelib.timeline_steps(entries) == [
        {"time": "0:00", "key": "Gm", "delta": ""},
        {"time": "3:57", "key": "G#m", "delta": "+1"},
        {"time": "4:49", "key": "Fm", "delta": "-3"},
        {"time": "5:00", "key": "F", "delta": "±0"},
    ]
    assert tonelib.timeline_steps("rác") == []
