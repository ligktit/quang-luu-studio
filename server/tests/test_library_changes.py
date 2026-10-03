"""Feed bản ghim cho máy khách: cursor keyset (last_seen, id), không sót, không lặp."""
from datetime import datetime

from app.db import SessionLocal
from app.models import License, SharedTone
from app.routers import library as library_router
from app.services import codegen


def _token(client, fp):
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=1, status="unused", plan="standard"))
        db.commit()
    return client.post("/api/v1/activate", json={"code": code, "device_fingerprint": fp}).json()["token"]


def _set(admin_client, song, key):
    return admin_client.post("/admin/library/set", data={
        "song_key": song, "title": "", "primary_key": key, "timeline": "",
    }, follow_redirects=False)


def _contribute(client, token, fp, song, key):
    return client.post("/api/v1/library/contribute", json={
        "token": token, "device_fingerprint": fp,
        "items": [{"song_key": song, "title": "t", "primary_key": key, "source": "auto",
                   "timeline": [{"time": 0, "key_display": key, "key_index": 0, "scale": "Major"}]}],
    })


def _changes(client, token, fp, cursor=""):
    res = client.post("/api/v1/library/changes", json={
        "token": token, "device_fingerprint": fp, "cursor": cursor,
    })
    assert res.status_code == 200, res.text
    return res.json()


def _song(n):
    return f"SONG{n:07d}"  # 11 ký tự


def test_cursor_rong_tra_ban_ghim_khong_tra_ban_thang_do_phieu(admin_client):
    fp = "may-feed-01"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, _song(1), "C")   # thắng do phiếu, không ghim
    _set(admin_client, _song(2), "F#m")                    # admin đặt → ghim

    body = _changes(admin_client, token, fp)
    assert body["ok"] is True
    assert [it["song_key"] for it in body["items"]] == [_song(2)]
    assert body["items"][0]["pinned"] is True
    assert body["items"][0]["source"] == "admin"
    assert body["items"][0]["timeline"][0]["key_display"] == "F#m"
    assert body["has_more"] is False
    assert body["next_cursor"]


def test_gui_lai_next_cursor_thi_rong_va_cursor_giu_nguyen(admin_client):
    fp = "may-feed-02"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")
    first = _changes(admin_client, token, fp)

    again = _changes(admin_client, token, fp, cursor=first["next_cursor"])
    assert again["items"] == []
    assert again["next_cursor"] == first["next_cursor"]
    assert again["has_more"] is False


def test_ban_moi_sau_cursor_xuat_hien(admin_client):
    fp = "may-feed-03"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")
    cur = _changes(admin_client, token, fp)["next_cursor"]

    _set(admin_client, _song(2), "Dm")
    body = _changes(admin_client, token, fp, cursor=cur)
    assert [it["song_key"] for it in body["items"]] == [_song(2)]


def test_cung_last_seen_vat_qua_ranh_gioi_trang_khong_sot_khong_lap(admin_client, monkeypatch):
    monkeypatch.setattr(library_router, "CHANGES_PAGE_SIZE", 2)
    fp = "may-feed-04"
    token = _token(admin_client, fp)
    for n in range(1, 6):
        _set(admin_client, _song(n), "Am")
    cung_gio = datetime(2026, 10, 3, 12, 0, 0, 500000)
    with SessionLocal() as db:
        for v in db.query(SharedTone).all():
            v.last_seen = cung_gio
        db.commit()

    seen, cursor, pages = [], "", 0
    while True:
        body = _changes(admin_client, token, fp, cursor=cursor)
        seen += [it["song_key"] for it in body["items"]]
        cursor = body["next_cursor"]
        pages += 1
        if not body["has_more"]:
            break
        assert pages < 10

    assert seen == [_song(n) for n in range(1, 6)]
    assert pages == 3  # 2 + 2 + 1


def test_has_more_dung_khi_vua_du_mot_trang(admin_client, monkeypatch):
    monkeypatch.setattr(library_router, "CHANGES_PAGE_SIZE", 2)
    fp = "may-feed-05"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")
    _set(admin_client, _song(2), "Am")

    body = _changes(admin_client, token, fp)
    assert len(body["items"]) == 2
    assert body["has_more"] is False, "đúng 2 bản, trang 2 → không còn gì, không được đoán theo == page size"


def test_cursor_hong_coi_nhu_rong(admin_client):
    fp = "may-feed-06"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")

    body = _changes(admin_client, token, fp, cursor="không-phải-cursor")
    assert body["ok"] is True
    assert [it["song_key"] for it in body["items"]] == [_song(1)]


def test_ban_ghim_bi_an_khong_vao_feed(admin_client):
    fp = "may-feed-07"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "Am")
    with SessionLocal() as db:
        tone_id = db.query(SharedTone).one().id
    admin_client.post(f"/admin/library/{tone_id}/hide")

    assert _changes(admin_client, token, fp)["items"] == []


def test_feed_can_may_da_kich_hoat(client):
    res = client.post("/api/v1/library/changes", json={
        "token": "tok-gia", "device_fingerprint": "may-la-xx", "cursor": "",
    })
    assert res.status_code in (401, 403)
    assert res.json()["ok"] is False


def test_xoa_ban_ghim_duy_nhat_roi_ghim_ban_khac(admin_client):
    """Xoá bản ghim duy nhất → bài không còn bản thắng, feed sau cursor cũ rỗng.
    Ghim bản khác → bản đó được bơm last_seen và xuất hiện sau cursor cũ."""
    fp = "may-feed-08"
    token = _token(admin_client, fp)
    _set(admin_client, _song(1), "F#m")
    cur = _changes(admin_client, token, fp)["next_cursor"]
    with SessionLocal() as db:
        admin_id = db.query(SharedTone).filter(SharedTone.song_key == _song(1)).one().id

    admin_client.post(f"/admin/library/{admin_id}/delete")
    assert _changes(admin_client, token, fp, cursor=cur)["items"] == []
    with SessionLocal() as db:
        assert db.query(SharedTone).filter(SharedTone.song_key == _song(1)).count() == 0

    _contribute(admin_client, token, fp, _song(1), "Bm")
    assert _changes(admin_client, token, fp, cursor=cur)["items"] == [], "bản máy dò thắng do phiếu không vào feed"
    with SessionLocal() as db:
        bm_id = db.query(SharedTone).filter(SharedTone.song_key == _song(1)).one().id
    admin_client.post(f"/admin/library/{bm_id}/pin")

    body = _changes(admin_client, token, fp, cursor=cur)
    assert [(it["song_key"], it["primary_key"]) for it in body["items"]] == [(_song(1), "Bm")]
