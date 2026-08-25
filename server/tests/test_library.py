"""Thư viện tone cộng đồng: gộp phiếu, ưu tiên bản người sửa tay, chống spam."""
from app.db import SessionLocal
from app.models import License
from app.services import codegen

SONG = "dQw4w9WgXcQ"


def _token(client, fp, plan="standard"):
    """Cấp license + kích hoạt cho một máy, trả token đã ký."""
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=1, status="unused", plan=plan))
        db.commit()
    return client.post("/api/v1/activate", json={"code": code, "device_fingerprint": fp}).json()["token"]


def _timeline(*pairs):
    return [
        {"time": t, "key_display": k, "key_index": 0, "scale": "Major"}
        for t, k in pairs
    ]


def _contribute(client, token, fp, timeline, source="auto", song=SONG, title="Bài test"):
    return client.post("/api/v1/library/contribute", json={
        "token": token,
        "device_fingerprint": fp,
        "items": [{
            "song_key": song, "title": title, "primary_key": timeline[0]["key_display"],
            "source": source, "timeline": timeline,
        }],
    })


def _lookup(client, token, fp, keys=(SONG,)):
    return client.post("/api/v1/library/lookup", json={
        "token": token, "device_fingerprint": fp, "keys": list(keys),
    })


def test_hai_may_dò_giong_nhau_thi_cong_phieu(client):
    fp1, fp2 = "may-so-mot", "may-so-hai"
    t1, t2 = _token(client, fp1), _token(client, fp2)
    tl = _timeline((0, "C Major"), (60, "G Major"))

    assert _contribute(client, t1, fp1, tl).json()["accepted"] == 1
    assert _contribute(client, t2, fp2, tl).json()["accepted"] == 1

    result = _lookup(client, t1, fp1).json()["results"][SONG]
    assert result["votes"] == 2, "cùng chuỗi tone phải gộp thành MỘT biến thể"
    assert result["primary_key"] == "C Major"
    assert len(result["timeline"]) == 2


def test_cung_mot_may_gui_nhieu_lan_van_chi_mot_phieu(client):
    fp = "may-spam"
    token = _token(client, fp)
    tl = _timeline((0, "C Major"))

    for _ in range(5):
        _contribute(client, token, fp, tl)

    assert _lookup(client, token, fp).json()["results"][SONG]["votes"] == 1


def test_confidence_khac_nhau_van_coi_la_mot_ket_qua(client):
    """Chuẩn hoá phải bỏ các trường dao động, nếu không không bao giờ gộp được."""
    fp1, fp2 = "may-alpha", "may-beta"
    t1, t2 = _token(client, fp1), _token(client, fp2)

    tl1 = [{"time": 0.2, "key_display": "C Major", "key_index": 0, "scale": "Major"}]
    tl2 = [{"time": 0.4, "key_display": "C Major", "key_index": 0, "scale": "Major"}]
    _contribute(client, t1, fp1, tl1)
    _contribute(client, t2, fp2, tl2)

    assert _lookup(client, t1, fp1).json()["results"][SONG]["votes"] == 2


def test_ban_nguoi_sua_tay_thang_ban_may_do_dong_hon(client):
    fps = ["may-auto-1", "may-auto-2", "may-nguoi"]
    tokens = [_token(client, fp) for fp in fps]
    auto_tl = _timeline((0, "A Minor"))
    human_tl = _timeline((0, "C Major"))

    _contribute(client, tokens[0], fps[0], auto_tl, source="auto")
    _contribute(client, tokens[1], fps[1], auto_tl, source="auto")
    _contribute(client, tokens[2], fps[2], human_tl, source="human")

    best = _lookup(client, tokens[0], fps[0]).json()["results"][SONG]
    assert best["source"] == "human"
    assert best["primary_key"] == "C Major"


def test_bao_sai_du_nhieu_thi_bien_the_bi_loai(client):
    fp1, fp2, fp3 = "may-gop-1", "may-bao-1", "may-bao-2"
    t1, t2, t3 = _token(client, fp1), _token(client, fp2), _token(client, fp3)
    tl = _timeline((0, "C Major"))
    _contribute(client, t1, fp1, tl)

    for token, fp in ((t2, fp2), (t3, fp3)):
        r = client.post("/api/v1/library/report", json={
            "token": token, "device_fingerprint": fp, "song_key": SONG,
        })
        assert r.status_code == 200, r.text

    # 1 phiếu thuận (auto) − 2×2 điểm phạt < 0 → không còn được trả về.
    assert _lookup(client, t1, fp1).json()["results"] == {}


def test_may_doi_y_thi_phieu_cu_bi_rut(client):
    """Sửa tay xong đóng góp bản mới: không được giữ phiếu cho cả hai biến thể."""
    fp = "may-doi-y"
    token = _token(client, fp)
    _contribute(client, token, fp, _timeline((0, "A Minor")), source="auto")
    _contribute(client, token, fp, _timeline((0, "C Major")), source="human")

    results = _lookup(client, token, fp).json()["results"]
    assert results[SONG]["primary_key"] == "C Major"
    assert results[SONG]["votes"] == 1

    # Biến thể cũ mất phiếu → điểm 0 → không còn đủ tư cách thắng.
    from app.models import SharedTone
    with SessionLocal() as db:
        old = db.query(SharedTone).filter(SharedTone.primary_key == "A Minor").one()
        assert old.votes == 0


def test_chi_nhan_video_id_youtube(client):
    """Đường dẫn file local là dữ liệu cá nhân — không bao giờ được lên server."""
    fp = "may-local"
    token = _token(client, fp)

    r = client.post("/api/v1/library/contribute", json={
        "token": token, "device_fingerprint": fp,
        "items": [{
            "song_key": "D:\\Nhac\\bai.mp3"[:11], "title": "x", "primary_key": "C Major",
            "source": "auto", "timeline": _timeline((0, "C Major")),
        }],
    })
    assert r.status_code == 200
    assert r.json()["rejected"] == 1 and r.json()["accepted"] == 0


def test_timeline_rong_bi_tu_choi(client):
    fp = "may-rong"
    token = _token(client, fp)
    r = client.post("/api/v1/library/contribute", json={
        "token": token, "device_fingerprint": fp,
        "items": [{"song_key": SONG, "title": "x", "source": "auto", "timeline": []}],
    })
    assert r.json()["rejected"] == 1


def test_may_chua_kich_hoat_khong_dung_duoc(client):
    r = client.post("/api/v1/library/lookup", json={
        "device_fingerprint": "may-la-mat", "keys": [SONG],
    })
    assert r.status_code == 401


def test_may_standard_van_dung_duoc(client):
    """Khác Cloud Sync: thư viện chung KHÔNG giới hạn ở Premium."""
    fp = "may-standard"
    token = _token(client, fp, plan="standard")

    assert _contribute(client, token, fp, _timeline((0, "C Major"))).status_code == 200
    assert SONG in _lookup(client, token, fp).json()["results"]


def test_bai_chua_ai_dong_gop_thi_tra_rong(client):
    fp = "may-hoi-bai"
    token = _token(client, fp)
    assert _lookup(client, token, fp, keys=["abcdefghijk"]).json()["results"] == {}


def test_dev_ghim_thi_thang_tuyet_doi(client):
    fps = ["may-nhieu-1", "may-nhieu-2", "may-it-phieu"]
    tokens = [_token(client, fp) for fp in fps]
    _contribute(client, tokens[0], fps[0], _timeline((0, "A Minor")), source="human")
    _contribute(client, tokens[1], fps[1], _timeline((0, "A Minor")), source="human")
    _contribute(client, tokens[2], fps[2], _timeline((0, "F Major")), source="auto")

    from app.models import SharedTone
    with SessionLocal() as db:
        tone = db.query(SharedTone).filter(SharedTone.primary_key == "F Major").one()
        tone.pinned = True
        db.commit()

    assert _lookup(client, tokens[0], fps[0]).json()["results"][SONG]["primary_key"] == "F Major"


def test_dev_an_bien_the_thi_khong_con_tra_ve(client):
    fp = "may-an-bien"
    token = _token(client, fp)
    _contribute(client, token, fp, _timeline((0, "C Major")))

    from app.models import SharedTone
    with SessionLocal() as db:
        db.query(SharedTone).filter(SharedTone.song_key == SONG).one().status = "hidden"
        db.commit()

    assert _lookup(client, token, fp).json()["results"] == {}


def test_admin_thay_bien_the_va_ghim_duoc(admin_client):
    fps = ["may-admin-1", "may-admin-2"]
    tokens = [_token(admin_client, fp) for fp in fps]
    _contribute(admin_client, tokens[0], fps[0], _timeline((0, "C Major"), (30, "G Major")))
    _contribute(admin_client, tokens[1], fps[1], _timeline((0, "A Minor")), source="auto")

    page = admin_client.get("/admin/library")
    assert page.status_code == 200
    assert SONG in page.text and "C Major" in page.text and "A Minor" in page.text

    from app.models import SharedTone
    with SessionLocal() as db:
        loser = db.query(SharedTone).filter(SharedTone.primary_key == "A Minor").one().id

    admin_client.post(f"/admin/library/{loser}/pin")
    assert _lookup(admin_client, tokens[0], fps[0]).json()["results"][SONG]["primary_key"] == "A Minor"

    admin_client.post(f"/admin/library/{loser}/hide")
    assert _lookup(admin_client, tokens[0], fps[0]).json()["results"][SONG]["primary_key"] == "C Major"


def test_admin_chi_ghim_duoc_mot_ban_moi_bai(admin_client):
    fps = ["may-ghim-1", "may-ghim-2"]
    tokens = [_token(admin_client, fp) for fp in fps]
    _contribute(admin_client, tokens[0], fps[0], _timeline((0, "C Major")))
    _contribute(admin_client, tokens[1], fps[1], _timeline((0, "A Minor")))

    from app.models import SharedTone
    with SessionLocal() as db:
        ids = [t.id for t in db.query(SharedTone).filter(SharedTone.song_key == SONG).all()]

    for tone_id in ids:
        admin_client.post(f"/admin/library/{tone_id}/pin")

    with SessionLocal() as db:
        pinned = db.query(SharedTone).filter(SharedTone.song_key == SONG, SharedTone.pinned).all()
    assert len(pinned) == 1, "ghim hai bản cho cùng một bài là mâu thuẫn tự thân"


def test_admin_xoa_bien_the(admin_client):
    fp = "may-xoa-01"
    token = _token(admin_client, fp)
    _contribute(admin_client, token, fp, _timeline((0, "C Major")))

    from app.models import SharedTone
    with SessionLocal() as db:
        tone_id = db.query(SharedTone).filter(SharedTone.song_key == SONG).one().id

    admin_client.post(f"/admin/library/{tone_id}/delete")
    assert _lookup(admin_client, token, fp).json()["results"] == {}
