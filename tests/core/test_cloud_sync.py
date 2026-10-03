"""core/licensing/sync.py — Cloud Sync (Premium) phía client.

Không đụng mạng thật: thay _request bằng hàm giả. Vì sao có file này: nút
"Đồng bộ ngay" từng treo hàng phút vì sync chạy 8 request tuần tự, mỗi cái
timeout 10s, và lần nào cũng đẩy nguyên file dù không đổi gì.
"""
import json
import threading
import time

import pytest

from core.licensing import sync


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    files = {kind: str(tmp_path / f"{kind}.json") for kind in sync.ALL_KINDS}
    monkeypatch.setattr(sync, "KIND_FILES", files)
    monkeypatch.setattr(sync, "_is_premium", lambda: True)
    monkeypatch.setattr(sync, "_server_base", lambda: "https://example.test")
    monkeypatch.setattr(sync, "_auth_fields", lambda: {
        "token": "tok", "code": "ABCD", "device_fingerprint": "fp-test",
    })
    monkeypatch.setattr(sync, "_state_path", lambda: str(tmp_path / "sync_state.json"))
    yield


def _write(kind, obj):
    with open(sync.KIND_FILES[kind], "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _fake_request(calls, delay=0.0, body=None):
    """Server giả: PUT nhận blob, GET trả đúng blob vừa nhận (như server thật).
    `body` ép mọi GET trả một thân cố định (vd. server trống)."""
    stored = {}

    def _request(method, path, payload):
        if delay:
            time.sleep(delay)
        calls.append((method, path))
        if method == "PUT":
            stored[path] = payload.get("data", "")
            return 200, {"ok": True, "version": 1}
        if body is not None:
            return 200, body
        kind_path = path.rsplit("/get", 1)[0]
        if kind_path in stored:
            return 200, {"ok": True, "exists": True, "version": 1, "data": stored[kind_path]}
        return 200, {"ok": True, "exists": False}
    return _request


# ── Push bỏ qua khi nội dung không đổi ──
def test_push_lan_hai_cung_noi_dung_thi_khong_goi_mang(monkeypatch):
    calls = []
    monkeypatch.setattr(sync, "_request", _fake_request(calls))
    _write("songs", [{"url": "https://youtu.be/dQw4w9WgXcQ", "title": "A"}])

    first = sync.push("songs")
    second = sync.push("songs")

    assert first["ok"] is True and "noop" not in first
    assert second["ok"] is True and second["noop"] == "unchanged"
    assert len([c for c in calls if c[0] == "PUT"]) == 1


def test_push_lai_khi_noi_dung_doi(monkeypatch):
    calls = []
    monkeypatch.setattr(sync, "_request", _fake_request(calls))
    _write("songs", [{"url": "https://youtu.be/dQw4w9WgXcQ", "title": "A"}])
    sync.push("songs")

    _write("songs", [{"url": "https://youtu.be/dQw4w9WgXcQ", "title": "B"}])
    result = sync.push("songs")

    assert "noop" not in result
    assert len([c for c in calls if c[0] == "PUT"]) == 2


def test_push_hong_thi_khong_ghi_nho_hash(monkeypatch):
    """Lần đẩy bị từ chối không được coi là 'đã đẩy' — lần sau phải đẩy lại."""
    _write("songs", [{"url": "https://youtu.be/dQw4w9WgXcQ"}])
    monkeypatch.setattr(sync, "_request", lambda m, p, b: (500, {"ok": False}))
    assert sync.push("songs")["ok"] is False

    calls = []
    monkeypatch.setattr(sync, "_request", _fake_request(calls))
    assert "noop" not in sync.push("songs")
    assert len(calls) == 1


# ── sync_all: song song, không chạy chồng ──
def test_sync_all_chay_cac_loai_song_song(monkeypatch):
    for kind in sync.ALL_KINDS:
        _write(kind, {"kind": kind})
    calls = []
    monkeypatch.setattr(sync, "_request", _fake_request(calls, delay=0.15))

    started = time.perf_counter()
    result = sync.sync_all()
    elapsed = time.perf_counter() - started

    assert result["ok"] is True
    assert len(calls) == 2 * len(sync.ALL_KINDS)
    # Tuần tự: 8 × 0,15s = 1,2s. Song song theo loại: ~0,3s.
    assert elapsed < 0.8, f"sync_all vẫn chạy tuần tự ({elapsed:.2f}s)"


def test_sync_all_dang_chay_thi_luot_sau_bo_qua(monkeypatch):
    release = threading.Event()

    def _slow(method, path, payload):
        release.wait(2.0)
        return 200, {"ok": True, "exists": False}

    for kind in sync.ALL_KINDS:
        _write(kind, {"kind": kind})
    monkeypatch.setattr(sync, "_request", _slow)

    first = {}
    t = threading.Thread(target=lambda: first.update(sync.sync_all()), daemon=True)
    t.start()
    time.sleep(0.1)
    second = sync.sync_all()
    release.set()
    t.join(3.0)

    assert second == {"skipped": "busy"}
    assert first.get("ok") is True


# ── Tóm tắt cho người đọc ──
def test_tom_tat_khi_xong_het():
    res = {"ok": True, "results": {
        k: {"push": {"ok": True, "kind": k}, "pull": {"ok": True, "kind": k}}
        for k in sync.ALL_KINDS
    }}
    assert sync.summarize(res) == "Đã đồng bộ xong (4/4 mục)."


def test_tom_tat_khi_mat_mang():
    res = {"ok": True, "results": {
        k: {"push": {"ok": False, "error": "offline", "kind": k},
            "pull": {"ok": False, "error": "offline", "kind": k}}
        for k in sync.ALL_KINDS
    }}
    assert sync.summarize(res) == "Không kết nối được máy chủ — sẽ tự thử lại sau."


def test_tom_tat_khi_mot_phan_loi():
    res = {"ok": True, "results": {
        "songs": {"push": {"ok": True}, "pull": {"ok": True}},
        "timelines": {"push": {"ok": True}, "pull": {"ok": True}},
        "tones": {"push": {"ok": False, "error": "http_500"}, "pull": {"ok": True}},
        "scores": {"push": {"ok": True}, "pull": {"ok": False, "error": "write_failed"}},
    }}
    text = sync.summarize(res)
    assert text.startswith("Đồng bộ 2/4 mục")
    assert "tones" in text and "scores" in text


def test_tom_tat_khong_premium_va_dang_chay():
    assert sync.summarize({"skipped": "not_premium"}) == "Chỉ dành cho gói Premium."
    assert sync.summarize({"skipped": "busy"}) == "Đang có lượt đồng bộ khác chạy — chờ xong rồi thử lại."


# ── Server mất dữ liệu / khôi phục bản cũ → phải đẩy lại dù hash không đổi ──
def test_server_khong_con_du_lieu_thi_sync_kind_day_lai_ngay(monkeypatch):
    _write("tones", {"a": 1})
    calls = []
    monkeypatch.setattr(sync, "_request", _fake_request(calls))
    sync.push("tones")                      # đã nhớ hash + version
    assert len([c for c in calls if c[0] == "PUT"]) == 1

    calls.clear()
    monkeypatch.setattr(sync, "_request", _fake_request(calls, body={"ok": True, "exists": False}))
    out = sync._sync_kind("tones")

    assert out["pull"]["noop"] == "no_remote_data"
    assert len([c for c in calls if c[0] == "PUT"]) == 1, "server trống → đẩy lại trong cùng lượt"
    assert out["repush"]["ok"] is True and "noop" not in out["repush"]


def test_server_lui_version_thi_giu_local_va_day_lai(monkeypatch):
    _write("tones", {"a": "moi"})
    calls = []

    def _req_v5(method, path, payload):
        calls.append((method, path))
        if method == "PUT":
            return 200, {"ok": True, "version": 5}
        return 200, {"ok": True, "exists": False}
    monkeypatch.setattr(sync, "_request", _req_v5)
    sync.push("tones")

    calls.clear()
    old_remote = json.dumps({"a": "cu"})

    def _req_rollback(method, path, payload):
        calls.append((method, path))
        if method == "PUT":
            return 200, {"ok": True, "version": 6}
        return 200, {"ok": True, "exists": True, "version": 1, "data": old_remote}
    monkeypatch.setattr(sync, "_request", _req_rollback)
    out = sync._sync_kind("tones")

    with open(sync.KIND_FILES["tones"], encoding="utf-8") as f:
        assert json.load(f) == {"a": "moi"}, "server lùi version thì local thắng, không bị bản cũ đè"
    assert out["pull"]["noop"] == "server_rolled_back"
    assert len([c for c in calls if c[0] == "PUT"]) == 1
    assert out["repush"]["version"] == 6
