"""Giao diện thư viện tone: danh sách gọn để tìm bài, trang riêng để sửa một bài."""
from app.db import SessionLocal
from app.models import SharedTone
from app.services import tonelib

SONG = "p4AOrAjZKr0"
OTHER = "aaaaaaaaaaa"


def _set(admin_client, **form):
    data = {"song_key": SONG, "title": "", "primary_key": "", "timeline": ""}
    data.update(form)
    return admin_client.post("/admin/library/set", data=data, follow_redirects=False)


def _ids(song=SONG):
    with SessionLocal() as db:
        return [t.id for t in db.query(SharedTone).filter(SharedTone.song_key == song).order_by(SharedTone.id)]


def test_song_key_from_input_hieu_ma_va_link_youtube():
    f = tonelib.song_key_from_input
    assert f(SONG) == SONG
    assert f(f"  https://www.youtube.com/watch?v={SONG}&t=30s ") == SONG
    assert f(f"https://youtu.be/{SONG}?si=abc") == SONG
    assert f(f"https://m.youtube.com/shorts/{SONG}") == SONG
    assert f(f"https://www.youtube.com/embed/{SONG}") == SONG
    assert f("Rất lâu rồi mới khóc") is None
    assert f("") is None


def test_danh_sach_moi_bai_mot_dong_co_link_sua(admin_client):
    _set(admin_client, title="Bài chuyển tone", timeline="0:00 Gm\n3:57 G#m")
    _set(admin_client, song_key=OTHER, title="Bài một tone", primary_key="Am")

    res = admin_client.get("/admin/library")
    assert res.status_code == 200
    assert f'href="/admin/library/song/{SONG}"' in res.text
    assert f'href="/admin/library/song/{OTHER}"' in res.text
    assert "Chuyển tone 1 lần" in res.text and "Một tone cả bài" in res.text
    assert "+1" in res.text and "3:57" in res.text
    # Danh sách chỉ để tìm: không còn form sửa/nút xoá trên từng bài.
    assert "/delete" not in res.text
    assert 'name="timeline"' not in res.text


def test_danh_sach_loc_bai_chuyen_tone(admin_client):
    _set(admin_client, title="Bài chuyển tone", timeline="0:00 Gm\n3:57 G#m")
    _set(admin_client, song_key=OTHER, title="Bài một tone", primary_key="Am")
    res = admin_client.get("/admin/library?multi=1")
    assert "Bài chuyển tone" in res.text and "Bài một tone" not in res.text


def test_dan_link_youtube_vao_o_tim_thi_mo_thang_trang_sua(admin_client):
    res = admin_client.get(f"/admin/library?q=https://youtu.be/{SONG}", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == f"/admin/library/song/{SONG}"


def test_go_ma_chua_co_thi_goi_y_dat_tone(admin_client):
    res = admin_client.get(f"/admin/library?q={OTHER}")
    assert res.status_code == 200
    assert f'href="/admin/library/song/{OTHER}"' in res.text
    assert "Đặt tone cho bài này" in res.text


def test_go_ma_da_co_thi_mo_thang_trang_sua(admin_client):
    _set(admin_client, primary_key="Am")
    res = admin_client.get(f"/admin/library?q={SONG}", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == f"/admin/library/song/{SONG}"


def test_trang_sua_co_trinh_phat_bang_moc_va_cac_ban(admin_client):
    _set(admin_client, title="Rất Lâu Rồi Mới Khóc", timeline="0:00 Cm\n4:14.5 C#\n4:49 C#m")
    _set(admin_client, timeline="0:00 Gm\n3:57 G#m")

    res = admin_client.get(f"/admin/library/song/{SONG}")
    assert res.status_code == 200
    assert "Rất Lâu Rồi Mới Khóc" in res.text
    assert f'data-video="{SONG}"' in res.text           # trình phát YouTube nhúng
    # Bảng mốc điền sẵn bản thắng (bản admin đặt sau cùng đang ghim).
    assert '"key": "G#m"' in res.text and '"time": "3:57"' in res.text
    assert 'action="/admin/library/set"' in res.text
    # Các bản khác: dùng lại được, ẩn/xoá phải qua xác nhận.
    assert res.text.count("small use-variant") == 2
    assert "C#m" in res.text
    assert "confirm(" in res.text
    assert "Chuyển tone 1 lần" in res.text


def test_trang_sua_bai_chua_co_van_mo_duoc(admin_client):
    res = admin_client.get(f"/admin/library/song/{OTHER}")
    assert res.status_code == 200
    assert f'data-video="{OTHER}"' in res.text
    assert "small use-variant" not in res.text


def test_trang_sua_ma_sai_thi_ve_danh_sach(admin_client):
    res = admin_client.get("/admin/library/song/ngan", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"].startswith("/admin/library")


def test_luu_ghim_an_xoa_deu_quay_ve_trang_sua(admin_client):
    res = _set(admin_client, timeline="0:00 Gm\n3:57 G#m")
    assert res.headers["location"].startswith(f"/admin/library/song/{SONG}?msg=")

    tone_id = _ids()[0]
    for action in ("pin", "hide", "delete"):
        res = admin_client.post(f"/admin/library/{tone_id}/{action}", follow_redirects=False)
        assert res.headers["location"] == f"/admin/library/song/{SONG}", action


def test_trang_sua_can_dang_nhap(client):
    res = client.get(f"/admin/library/song/{SONG}", follow_redirects=False)
    assert res.status_code in (302, 303, 401)


def test_moi_dong_co_nut_sua_ro_rang(admin_client):
    _set(admin_client, primary_key="Am")
    res = admin_client.get("/admin/library")
    assert f'<a class="edit-btn" href="/admin/library/song/{SONG}">Sửa →</a>' in res.text
