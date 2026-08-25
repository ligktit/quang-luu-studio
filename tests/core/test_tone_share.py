"""core/tone_share.py — thư viện tone cộng đồng phía client.

Không đụng mạng thật: mọi test đều thay _post bằng hàm giả.
"""
import json

import pytest

from core import tone_share

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
KEY = "dQw4w9WgXcQ"
LOCAL = r"D:\Nhac\bai-hat.mp3"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(tone_share, "_server_base", lambda: "https://example.test")
    monkeypatch.setattr(tone_share, "_has_license", lambda: True)
    monkeypatch.setattr(tone_share, "_auth_fields", lambda: {
        "token": "tok", "device_fingerprint": "fingerprint-test",
    })
    monkeypatch.setattr(tone_share, "_queue_path", lambda: str(tmp_path / "tone_share_queue.json"))
    monkeypatch.setattr(tone_share, "_save_local", lambda url, entry: None)
    # Mặc định: settings không tắt tính năng.
    monkeypatch.setattr(
        "core.config.ConfigManager.load_settings", staticmethod(lambda: {})
    )
    # Chạy MỌI thread nền ngay tại chỗ. Không làm vậy thì flush_queue() bên
    # trong contribute() đẻ ra daemon thread sống lâu hơn cả test — teardown gỡ
    # monkeypatch xong, thread mới thức dậy và ghi thẳng vào file thật của người
    # dùng ở thư mục dự án.
    monkeypatch.setattr(
        tone_share.threading, "Thread",
        lambda target, daemon=True: type("T", (), {"start": lambda _s: target()})(),
    )
    tone_share.clear_session_cache()
    yield
    tone_share.clear_session_cache()


def _fake_post(status, body, sink=None):
    def _post(path, payload):
        if sink is not None:
            sink.append((path, payload))
        return status, body
    return _post


def _result(primary="C Major", votes=2):
    return {
        "song_key": KEY, "title": "Bài test", "primary_key": primary,
        "source": "human", "votes": votes, "payload_hash": "hash-abc",
        "timeline": [{"time": 0, "key_display": primary, "key_index": 0, "scale": "Major"}],
    }


# ── Điều kiện bật/tắt ──
def test_tat_trong_thiet_lap_thi_khong_goi_mang(monkeypatch):
    monkeypatch.setattr(
        "core.config.ConfigManager.load_settings",
        staticmethod(lambda: {"tone_share": {"enabled": False}}),
    )
    called = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {}, called))

    assert tone_share.enabled() is False
    assert tone_share.lookup(URL) is None
    assert not called


def test_may_chua_kich_hoat_thi_khong_goi_mang(monkeypatch):
    monkeypatch.setattr(tone_share, "_has_license", lambda: False)
    called = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {}, called))

    assert tone_share.lookup(URL) is None
    assert not called


# ── Tra cứu ──
def test_lookup_tra_entry_kieu_tone_cache(monkeypatch):
    saved = []
    monkeypatch.setattr(tone_share, "_save_local", lambda url, entry: saved.append((url, entry)))
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True, "results": {KEY: _result()}}))

    entry = tone_share.lookup(URL)

    assert entry["primary_key"] == "C Major"
    assert entry["key_timeline"][0]["key_display"] == "C Major"
    assert entry["origin"] == "community"
    assert entry["payload_hash"] == "hash-abc"
    assert saved == [(URL, entry)], "trúng thì phải ghi xuống cache local để dùng offline"


def test_bai_file_local_khong_bao_gio_gui_len(monkeypatch):
    called = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True, "results": {}}, called))

    assert tone_share.song_key(LOCAL) is None
    assert tone_share.lookup(LOCAL) is None
    assert tone_share.contribute(LOCAL, "Bài local", {"key_timeline": [{"key_display": "C"}]}) is False
    assert not called, "đường dẫn file trong máy là dữ liệu cá nhân"


def test_khong_hoi_lai_bai_vua_tra_hut(monkeypatch):
    calls = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True, "results": {}}, calls))

    assert tone_share.lookup(URL) is None
    assert tone_share.lookup(URL) is None

    assert len(calls) == 1, "bài server không có thì đừng hỏi lại mỗi lần mở"


def test_lan_thu_hai_dung_lai_ket_qua_trong_phien(monkeypatch):
    calls = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True, "results": {KEY: _result()}}, calls))

    first = tone_share.lookup(URL)
    second = tone_share.lookup(URL)

    assert first == second and len(calls) == 1


def test_mat_mang_thi_tra_none_chu_khong_no(monkeypatch):
    monkeypatch.setattr(tone_share, "_post", _fake_post(0, {}))
    assert tone_share.lookup(URL) is None


def test_lookup_many_gom_cac_link_cung_video(monkeypatch):
    sink = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True, "results": {KEY: _result()}}, sink))

    found = tone_share.lookup_many([URL, f"https://youtu.be/{KEY}", LOCAL])

    assert sink[0][1]["keys"] == [KEY], "hai link cùng một video chỉ hỏi một lần"
    assert set(found) == {URL, f"https://youtu.be/{KEY}"}


# ── Đóng góp ──
def test_contribute_xep_hang_va_gui(monkeypatch, tmp_path):
    sink = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True, "accepted": 1}, sink))

    ok = tone_share.contribute(URL, "Bài test", {
        "primary_key": "C Major",
        "key_timeline": [
            {"time": 0, "key_display": "C Major", "key_index": 0, "scale": "Major", "confidence": 0.9},
        ],
    })

    assert ok is True
    path, payload = sink[0]
    assert path == "/api/v1/library/contribute"
    item = payload["items"][0]
    assert item["song_key"] == KEY and item["source"] == "auto"
    assert "confidence" not in item["timeline"][0], "chỉ gửi phần cốt lõi của chuỗi tone"
    assert json.loads((tmp_path / "tone_share_queue.json").read_text(encoding="utf-8")) == []


def test_khong_gui_nguoc_lai_thu_vua_tai_ve(monkeypatch):
    """Gửi lại bản vừa tải về là tự bơm phiếu cho chính nó, không phải bằng chứng."""
    called = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True}, called))

    ok = tone_share.contribute(URL, "Bài test", {
        "primary_key": "C Major", "origin": "community",
        "key_timeline": [{"time": 0, "key_display": "C Major"}],
    })

    assert ok is False and not called


def test_ban_nguoi_sua_tay_van_gui_du_lay_tu_cong_dong(monkeypatch):
    """Người dùng sửa bản cộng đồng ⇒ đó là dữ liệu MỚI, phải được gửi."""
    sink = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True}, sink))

    ok = tone_share.contribute(URL, "Bài test", {
        "primary_key": "A Minor", "origin": "community",
        "key_timeline": [{"time": 0, "key_display": "A Minor"}],
    }, source="human")

    assert ok is True
    assert sink[0][1]["items"][0]["source"] == "human"


def test_timeline_rong_thi_khong_gui(monkeypatch):
    called = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True}, called))

    assert tone_share.contribute(URL, "x", {"key_timeline": []}) is False
    assert not called


def test_mat_mang_thi_giu_lai_dong_gop(monkeypatch, tmp_path):
    monkeypatch.setattr(tone_share, "_post", _fake_post(0, {}))

    tone_share.contribute(URL, "Bài test", {
        "primary_key": "C Major",
        "key_timeline": [{"time": 0, "key_display": "C Major"}],
    })

    queued = json.loads((tmp_path / "tone_share_queue.json").read_text(encoding="utf-8"))
    assert len(queued) == 1 and queued[0]["item"]["song_key"] == KEY


def test_server_tu_choi_thi_bo_chu_khong_ket_hang_doi(monkeypatch, tmp_path):
    monkeypatch.setattr(tone_share, "_post", _fake_post(422, {"ok": False, "message": "sai"}))

    tone_share.contribute(URL, "Bài test", {
        "primary_key": "C Major",
        "key_timeline": [{"time": 0, "key_display": "C Major"}],
    })

    assert json.loads((tmp_path / "tone_share_queue.json").read_text(encoding="utf-8")) == []


# ── Báo sai ──
def test_report_wrong_gui_va_quen_ket_qua_cu(monkeypatch):
    sink = []
    monkeypatch.setattr(
        tone_share, "_post",
        _fake_post(200, {"ok": True, "results": {KEY: _result()}}, sink),
    )

    assert tone_share.lookup(URL) is not None  # nạp vào cache phiên

    tone_share.report_wrong(URL, "hash-abc")

    report_calls = [c for c in sink if c[0] == "/api/v1/library/report"]
    assert report_calls and report_calls[0][1]["song_key"] == KEY

    # Đã báo sai thì không được tiếp tục phục vụ bản cũ từ cache phiên.
    sink.clear()
    tone_share.lookup(URL)
    assert any(c[0] == "/api/v1/library/lookup" for c in sink)
