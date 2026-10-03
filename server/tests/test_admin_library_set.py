"""Admin đặt tone trên /admin/library — bản admin thắng, tự ghim, bơm last_seen."""
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import License, SharedTone
from app.services import codegen

SONG = "pMPvJE1wwnc"


def _token(client, fp):
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=1, status="unused", plan="standard"))
        db.commit()
    return client.post("/api/v1/activate", json={"code": code, "device_fingerprint": fp}).json()["token"]


def _contribute(client, token, fp, key, song=SONG):
    return client.post("/api/v1/library/contribute", json={
        "token": token, "device_fingerprint": fp,
        "items": [{"song_key": song, "title": "Bài test", "primary_key": key, "source": "auto",
                   "timeline": [{"time": 0, "key_display": key, "key_index": 0, "scale": "Minor"}]}],
    })


def _lookup(client, token, fp, song=SONG):
    res = client.post("/api/v1/library/lookup", json={
        "token": token, "device_fingerprint": fp, "keys": [song],
    })
    return res.json()["results"].get(song)


def _set(admin_client, **form):
    data = {"song_key": SONG, "title": "", "primary_key": "", "timeline": ""}
    data.update(form)
    return admin_client.post("/admin/library/set", data=data, follow_redirects=False)


def _variants(song=SONG):
    with SessionLocal() as db:
        return db.query(SharedTone).filter(SharedTone.song_key == song).order_by(SharedTone.id).all()


def test_dat_tone_cho_bai_chua_co(admin_client):
    fp = "may-dat-01"
    token = _token(admin_client, fp)

    res = _set(admin_client, primary_key="F#m", title="Lưng Cha Bụng Mẹ")
    assert res.status_code == 303
    assert "/admin/library?q=" + SONG in res.headers["location"]

    found = _lookup(admin_client, token, fp)
    assert found["primary_key"] == "F#m"
    assert found["source"] == "admin"
    assert found["title"] == "Lưng Cha Bụng Mẹ"
    assert found["timeline"] == [{"time": 0.0, "key_display": "F#m", "key_index": 6, "scale": "Minor"}]
    assert _variants()[0].pinned is True


def test_dat_tone_de_ban_may_do_dang_thang(admin_client):
    fp = "may-dat-02"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, "Bm")
    assert _lookup(admin_client, token, fp)["primary_key"] == "Bm"

    _set(admin_client, primary_key="F#m")

    assert _lookup(admin_client, token, fp)["primary_key"] == "F#m"
    pinned = [v.pinned for v in _variants()]
    assert pinned == [False, True], "chỉ bản admin được ghim, bản máy dò bị bỏ ghim"


def test_dat_tone_nhieu_moc_doc_dung_mm_ss(admin_client):
    fp = "may-dat-03"
    token = _token(admin_client, fp)
    _set(admin_client, primary_key="F#m", timeline="0:00 F#m\n1:35 Bm")

    tl = _lookup(admin_client, token, fp)["timeline"]
    assert [(e["time"], e["key_display"]) for e in tl] == [(0.0, "F#m"), (95.0, "Bm")]


def test_dat_tone_trung_chuoi_voi_ban_cu_thi_nang_ban_cu_len_admin(admin_client):
    fp = "may-dat-04"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, "F#m")  # máy dò ra đúng rồi

    _set(admin_client, primary_key="F#m")

    vs = _variants()
    assert len(vs) == 1, "cùng payload_hash thì không đẻ biến thể mới"
    assert vs[0].source == "admin" and vs[0].pinned is True


def test_tone_sai_cu_phap_thi_khong_ghi_gi(admin_client):
    res = _set(admin_client, primary_key="Xm")
    assert res.status_code == 303
    assert "msg=" in res.headers["location"]
    assert _variants() == []

    res = _set(admin_client, primary_key="F#m", timeline="0:00 F#m\n1:35")
    assert _variants() == []


def test_ma_video_sai_thi_khong_ghi_gi(admin_client):
    res = _set(admin_client, song_key="ngan", primary_key="F#m")
    assert res.status_code == 303
    assert _variants("ngan") == []


def test_dat_tone_can_dang_nhap_admin(client):
    res = client.post("/admin/library/set", data={"song_key": SONG, "primary_key": "F#m"},
                      follow_redirects=False)
    assert res.status_code in (302, 303, 307)
    assert _variants() == []


def test_ghim_ban_khac_thi_ban_do_duoc_bom_last_seen(admin_client):
    """Feed /changes dựa vào last_seen: admin đổi bản thắng thì bản thắng mới phải mới lên."""
    fp = "may-dat-05"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, "Bm")
    _set(admin_client, primary_key="F#m")
    old_id = _variants()[0].id  # bản Bm của máy dò

    cu = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with SessionLocal() as db:
        for v in db.query(SharedTone).all():
            v.last_seen = cu
        db.commit()

    admin_client.post(f"/admin/library/{old_id}/pin")

    vs = {v.id: v for v in _variants()}
    assert vs[old_id].pinned is True
    assert vs[old_id].last_seen.replace(tzinfo=timezone.utc) > cu + timedelta(days=1)


def test_an_ban_ghim_thi_ban_thang_moi_duoc_bom_last_seen(admin_client):
    fp = "may-dat-06"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, "Bm")
    _set(admin_client, primary_key="F#m")
    bm_id, admin_id = [v.id for v in _variants()]

    cu = datetime(2020, 1, 1, tzinfo=timezone.utc)
    with SessionLocal() as db:
        for v in db.query(SharedTone).all():
            v.last_seen = cu
        db.commit()

    admin_client.post(f"/admin/library/{admin_id}/hide")

    vs = {v.id: v for v in _variants()}
    # Bản admin bị ẩn → bản Bm (1 phiếu auto) thắng lại và phải được bơm last_seen.
    assert vs[bm_id].last_seen.replace(tzinfo=timezone.utc) > cu + timedelta(days=1)


def test_trang_thu_vien_hien_thong_bao_va_form(admin_client):
    res = admin_client.get("/admin/library?msg=Xin+ch%C3%A0o")
    assert res.status_code == 200
    assert "Xin chào" in res.text
    assert 'action="/admin/library/set"' in res.text
