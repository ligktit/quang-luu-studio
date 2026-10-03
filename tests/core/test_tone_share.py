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


# ── Số đo lượt máy dò (diag) — dữ liệu nội bộ cho dev chấm thuật toán ──
_AUTO = {"primary_key": "Am", "key_timeline": [{"time": 0, "key_display": "Am", "key_index": 9, "scale": "Minor"}]}


def test_may_do_gui_kem_so_do(monkeypatch):
    sink = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True}, sink))
    monkeypatch.setattr(tone_share, "_app_version", lambda: "1.7.6")

    tone_share.contribute(URL, "Bài test", _AUTO, diag={
        "mode": "nhanh", "audio": "youtube", "confidence": 0.8123456, "tuning_cents": -46.04,
    })

    diag = sink[0][1]["items"][0]["diag"]
    assert diag == {"mode": "nhanh", "audio": "youtube", "confidence": 0.8123,
                    "tuning_cents": -46.04, "app_version": "1.7.6"}


def test_ban_nguoi_sua_khong_gui_so_do(monkeypatch):
    sink = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True}, sink))
    tone_share.contribute(URL, "Bài test", _AUTO, source="human", diag={"mode": "nhanh"})
    assert "diag" not in sink[0][1]["items"][0]


def test_khong_co_so_do_thi_khong_gui_truong_diag(monkeypatch):
    sink = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True}, sink))
    tone_share.contribute(URL, "Bài test", _AUTO)
    assert "diag" not in sink[0][1]["items"][0]


def test_so_do_la_bi_kep_ve_mien_hop_le(monkeypatch):
    """Server từ chối CẢ GÓI nếu một số đo vượt miền — không được làm mất tone đi kèm."""
    sink = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {"ok": True}, sink))
    tone_share.contribute(URL, "Bài test", _AUTO, diag={
        "mode": "x" * 50, "confidence": float("nan"), "tuning_cents": 500, "audio": None,
    })
    diag = sink[0][1]["items"][0]["diag"]
    assert diag["confidence"] is None
    assert diag["tuning_cents"] == 100.0
    assert len(diag["mode"]) == 20
    assert diag["audio"] == ""


# ── Bản admin đặt: pull_overrides ──
ADMIN_KEY = "pMPvJE1wwnc"
ADMIN_URL = f"https://www.youtube.com/watch?v={ADMIN_KEY}"


def _change(key=ADMIN_KEY, primary="F#m"):
    return {
        "song_key": key, "title": "Lưng Cha Bụng Mẹ", "primary_key": primary,
        "source": "admin", "pinned": True, "votes": 0, "payload_hash": f"hash-{key}",
        "timeline": [{"time": 0, "key_display": primary, "key_index": 6, "scale": "Minor"}],
    }


@pytest.fixture
def overrides_env(tmp_path, monkeypatch):
    """Cô lập file cursor + ghi cache + thiết lập bài; trả dict ghi lại các lần ghi."""
    saved, songs = [], []
    monkeypatch.setattr(tone_share, "_overrides_state_path",
                        lambda: str(tmp_path / "tone_overrides_state.json"))
    monkeypatch.setattr(tone_share, "_save_local", lambda url, entry: saved.append((url, entry)))
    monkeypatch.setattr(tone_share, "_update_saved_song_tone",
                        lambda url, primary: songs.append((url, primary)))
    monkeypatch.setattr("core.tone_cache.ManualToneTimeline.get_timeline_source",
                        staticmethod(lambda url: None))
    return {"saved": saved, "songs": songs}


def _paged_post(pages, calls):
    """pages: {cursor_nhận: (status, body)}. Ghi lại cursor từng lần gọi."""
    def _post(path, payload):
        assert path == "/api/v1/library/changes"
        calls.append(payload.get("cursor", ""))
        return pages[payload.get("cursor", "")]
    return _post


def test_pull_overrides_ghi_cache_origin_admin_va_luu_cursor(monkeypatch, overrides_env):
    calls = []
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change()], "next_cursor": "CUR-1", "has_more": False}),
    }, calls))

    stats = tone_share.pull_overrides()

    assert stats["ok"] is True
    assert stats["applied"] == 1 and stats["fetched"] == 1
    (url, entry), = overrides_env["saved"]
    assert url == ADMIN_URL
    assert entry["origin"] == "admin"
    assert entry["primary_key"] == "F#m"
    assert entry["key_timeline"][0]["key_display"] == "F#m"
    assert entry["payload_hash"] == f"hash-{ADMIN_KEY}"
    assert overrides_env["songs"] == [(ADMIN_URL, "F#m")]
    assert tone_share._load_cursor() == "CUR-1"
    assert calls == [""]


def test_pull_overrides_lan_sau_gui_cursor_da_luu(monkeypatch, overrides_env):
    tone_share._save_cursor("CUR-1")
    calls = []
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "CUR-1": (200, {"ok": True, "items": [], "next_cursor": "CUR-1", "has_more": False}),
    }, calls))

    stats = tone_share.pull_overrides()
    assert calls == ["CUR-1"]
    assert stats["applied"] == 0
    assert tone_share._load_cursor() == "CUR-1"


def test_pull_overrides_khong_de_chuoi_tone_khach_sua_tay(monkeypatch, overrides_env):
    monkeypatch.setattr("core.tone_cache.ManualToneTimeline.get_timeline_source",
                        staticmethod(lambda url: "human"))
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change()], "next_cursor": "CUR-1", "has_more": False}),
    }, []))

    stats = tone_share.pull_overrides()

    assert stats["skipped_human"] == 1 and stats["applied"] == 0
    assert overrides_env["saved"] == []
    assert overrides_env["songs"] == []
    assert tone_share._load_cursor() == "CUR-1", "bỏ qua là quyết định cuối, không lấy lại bản đó"


def test_pull_overrides_lap_trang_khi_has_more(monkeypatch, overrides_env):
    calls = []
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change("AAAAAAAAAAA")], "next_cursor": "CUR-1", "has_more": True}),
        "CUR-1": (200, {"ok": True, "items": [_change("BBBBBBBBBBB")], "next_cursor": "CUR-2", "has_more": False}),
    }, calls))

    stats = tone_share.pull_overrides()

    assert calls == ["", "CUR-1"]
    assert stats["applied"] == 2 and stats["pages"] == 2
    assert tone_share._load_cursor() == "CUR-2"


def test_pull_overrides_mat_mang_o_trang_hai_giu_cursor_trang_mot(monkeypatch, overrides_env):
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change("AAAAAAAAAAA")], "next_cursor": "CUR-1", "has_more": True}),
        "CUR-1": (0, {}),
    }, []))

    stats = tone_share.pull_overrides()

    assert stats["ok"] is False
    assert stats["applied"] == 1
    assert tone_share._load_cursor() == "CUR-1", "trang 1 đã áp xong thì giữ; trang 2 lấy lại lần sau"


def test_pull_overrides_server_tu_choi_khong_doi_cursor(monkeypatch, overrides_env):
    tone_share._save_cursor("CUR-0")
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "CUR-0": (403, {"ok": False, "message": "hết hạn"}),
    }, []))

    stats = tone_share.pull_overrides()
    assert stats["ok"] is False
    assert tone_share._load_cursor() == "CUR-0"


def test_pull_overrides_dung_o_tran_trang(monkeypatch, overrides_env):
    monkeypatch.setattr(tone_share, "CHANGES_MAX_PAGES", 3)
    calls = []
    monkeypatch.setattr(tone_share, "_post", lambda path, payload: (
        calls.append(payload["cursor"]) or (200, {
            "ok": True, "items": [_change()], "next_cursor": f"CUR-{len(calls)}", "has_more": True,
        })))

    stats = tone_share.pull_overrides()
    assert stats["pages"] == 3 and len(calls) == 3
    assert tone_share._load_cursor() == "CUR-3"


def test_pull_overrides_bo_qua_item_hong(monkeypatch, overrides_env):
    hong = {"song_key": "ngan", "timeline": []}
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [hong, _change()], "next_cursor": "CUR-1", "has_more": False}),
    }, []))

    stats = tone_share.pull_overrides()
    assert stats["applied"] == 1 and stats["fetched"] == 2
    assert len(overrides_env["saved"]) == 1


def test_pull_overrides_tat_trong_thiet_lap_thi_khong_goi_mang(monkeypatch, overrides_env):
    monkeypatch.setattr(
        "core.config.ConfigManager.load_settings",
        staticmethod(lambda: {"tone_share": {"enabled": False}}),
    )
    called = []
    monkeypatch.setattr(tone_share, "_post", _fake_post(200, {}, called))

    stats = tone_share.pull_overrides()
    assert stats == {"ok": False, "skipped": "disabled", "fetched": 0, "applied": 0,
                     "skipped_human": 0, "pages": 0}
    assert not called


def test_pull_overrides_xoa_dem_phien_cua_bai_vua_nhan(monkeypatch, overrides_env):
    tone_share._remember_miss(ADMIN_KEY)
    monkeypatch.setattr(tone_share, "_post", _paged_post({
        "": (200, {"ok": True, "items": [_change()], "next_cursor": "CUR-1", "has_more": False}),
    }, []))

    tone_share.pull_overrides()
    assert tone_share._recently_missed(ADMIN_KEY) is False
    with tone_share._cache_lock:
        assert tone_share._hit_cache[ADMIN_KEY]["origin"] == "admin"
