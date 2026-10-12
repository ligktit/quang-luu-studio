import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import VelopackRelease


def _rows():
    with SessionLocal() as db:
        return db.query(VelopackRelease).order_by(VelopackRelease.id).all()


def test_nhap_tao_dong_va_chay_nen(admin_client):
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        r = admin_client.post("/admin/velopack/import", data={"version": "v1.9.1"}, follow_redirects=False)
    assert r.status_code == 303
    rows = _rows()
    assert [(x.version, x.status) for x in rows] == [("1.9.1", "dang_nhap")]
    imp.assert_called_once_with(rows[0].id, rows[0].import_token)
    assert re.fullmatch(r"[0-9a-f]{32}", rows[0].import_token)
    assert rows[0].import_started_at is not None


def test_nhap_lai_cung_phien_ban(admin_client):
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        admin_client.post("/admin/velopack/import", data={"version": "1.9.1"})
        with SessionLocal() as db:
            row = db.query(VelopackRelease).one()
            row.status, row.import_error = "loi", "x"
            db.commit()
        admin_client.post("/admin/velopack/import", data={"version": "1.9.1"})
    rows = _rows()
    assert len(rows) == 1 and rows[0].status == "dang_nhap" and rows[0].import_error is None
    assert imp.call_count == 2


def test_khong_nhap_lai_ban_da_xong(admin_client):
    with SessionLocal() as db:
        db.add(VelopackRelease(version="1.9.1", status="xong", is_active=True, rollout_percent=100))
        db.commit()
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        r = admin_client.post("/admin/velopack/import", data={"version": "1.9.1"}, follow_redirects=False)
    assert r.status_code == 303
    row = _rows()[0]
    assert row.status == "xong" and row.is_active is True and row.rollout_percent == 100
    assert row.import_error is None
    imp.assert_not_called()


def test_phien_ban_sai_dinh_dang_bo_qua(admin_client):
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        admin_client.post("/admin/velopack/import", data={"version": "abc; rm -rf"})
    assert _rows() == []
    imp.assert_not_called()


def test_bat_tat_va_rollout(admin_client):
    with SessionLocal() as db:
        db.add(VelopackRelease(version="1.9.1", status="xong"))
        db.commit()
        rid = db.query(VelopackRelease).one().id
    admin_client.post(f"/admin/velopack/{rid}/toggle")
    admin_client.post(f"/admin/velopack/{rid}/rollout", data={"rollout_percent": "150"})
    row = _rows()[0]
    assert row.is_active is True and row.rollout_percent == 100


def test_trang_phien_ban_hien_bang_velopack(admin_client):
    with SessionLocal() as db:
        db.add(VelopackRelease(version="1.9.1", status="loi", import_error="Release v1.9.1 thiếu releases.win.json"))
        db.commit()
    html = admin_client.get("/admin/versions").text
    assert "1.9.1" in html and "thiếu releases.win.json" in html


def test_can_dang_nhap(client):
    r = client.post("/admin/velopack/import", data={"version": "1.9.1"}, follow_redirects=False)
    assert r.status_code in (302, 303, 401)
    assert _rows() == []


def test_phien_ban_chu_so_unicode_hoac_qua_dai_bi_bo_qua(admin_client):
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        admin_client.post("/admin/velopack/import", data={"version": "١.٩.١"})
        admin_client.post("/admin/velopack/import", data={"version": "1.9.1-" + "a" * 40})
    assert _rows() == []
    imp.assert_not_called()


def _add_row(**kw):
    with SessionLocal() as db:
        row = VelopackRelease(version="1.9.1", **kw)
        db.add(row)
        db.commit()
        return row.id


def test_khong_nhap_lai_khi_dang_nhap_con_moi(admin_client):
    started = datetime.now(timezone.utc) - timedelta(minutes=5)
    _add_row(status="dang_nhap", import_started_at=started, import_token="a" * 32)
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        r = admin_client.post("/admin/velopack/import", data={"version": "1.9.1"}, follow_redirects=False)
    assert r.status_code == 303
    imp.assert_not_called()
    assert _rows()[0].import_token == "a" * 32


def test_nhap_lai_khi_dang_nhap_da_qua_30_phut(admin_client):
    started = datetime.now(timezone.utc) - timedelta(minutes=31)
    _add_row(status="dang_nhap", import_started_at=started, import_token="a" * 32)
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        admin_client.post("/admin/velopack/import", data={"version": "1.9.1"})
    row = _rows()[0]
    imp.assert_called_once_with(row.id, row.import_token)
    assert row.import_token != "a" * 32


def test_nhap_lai_khi_dang_nhap_chua_co_moc_thoi_gian(admin_client):
    _add_row(status="dang_nhap")
    with patch("app.routers.admin.velopack_import.import_release") as imp:
        admin_client.post("/admin/velopack/import", data={"version": "1.9.1"})
    imp.assert_called_once()


def test_gui_doi_khong_loi_500(admin_client):
    """Hai request cùng thấy chưa có dòng: request thứ hai đụng UNIQUE → bỏ qua, không 500."""
    _add_row(status="dang_nhap", import_started_at=datetime.now(timezone.utc))
    with patch("app.routers.admin.velopack_import.import_release") as imp, \
            patch.object(Session, "scalar", return_value=None):
        r = admin_client.post("/admin/velopack/import", data={"version": "1.9.1"}, follow_redirects=False)
    assert r.status_code == 303
    imp.assert_not_called()
    assert len(_rows()) == 1


def _release_with_files(version, names, setup=None, **kw):
    import json
    from app.services import velopack_feed
    for n in list(names) + ([setup] if setup else []):
        (velopack_feed.velopack_dir() / n).write_bytes(b"x")
    assets = [{"FileName": n, "Type": "Full"} for n in names]
    with SessionLocal() as db:
        row = VelopackRelease(version=version, status="xong", assets_json=json.dumps(assets),
                              setup_filename=setup, **kw)
        db.add(row)
        db.commit()
        return row.id


def test_xoa_ban_dang_tat_xoa_dong_va_file(admin_client):
    from app.services import velopack_feed
    rid = _release_with_files("1.9.1", ["a-full.nupkg", "a-delta.nupkg"], setup="1.9.1_setup.exe")
    r = admin_client.post(f"/admin/velopack/{rid}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert _rows() == []
    assert list(velopack_feed.velopack_dir().iterdir()) == []


def test_khong_xoa_ban_dang_bat(admin_client):
    from app.services import velopack_feed
    rid = _release_with_files("1.9.1", ["a-full.nupkg"], is_active=True, rollout_percent=100)
    admin_client.post(f"/admin/velopack/{rid}/delete")
    assert len(_rows()) == 1
    assert (velopack_feed.velopack_dir() / "a-full.nupkg").exists()


def test_xoa_giu_file_dung_chung_voi_dong_khac(admin_client):
    from app.services import velopack_feed
    rid = _release_with_files("1.9.1", ["shared.nupkg", "only1.nupkg"])
    _release_with_files("1.9.2", ["shared.nupkg"], is_active=True)
    admin_client.post(f"/admin/velopack/{rid}/delete")
    d = velopack_feed.velopack_dir()
    assert (d / "shared.nupkg").exists() and not (d / "only1.nupkg").exists()
    assert [x.version for x in _rows()] == ["1.9.2"]


def test_xoa_khong_dung_ten_file_la(admin_client):
    from app.services import velopack_feed
    outside = velopack_feed.velopack_dir().parent / "keep.txt"
    outside.write_text("k")
    rid = _release_with_files("1.9.1", ["a.nupkg"])
    with SessionLocal() as db:
        row = db.get(VelopackRelease, rid)
        row.assets_json = '[{"FileName": "../keep.txt"}, {"FileName": "a.nupkg"}]'
        db.commit()
    admin_client.post(f"/admin/velopack/{rid}/delete")
    assert outside.exists()
    assert not (velopack_feed.velopack_dir() / "a.nupkg").exists()


def test_xoa_dong_khong_ton_tai_khong_loi(admin_client):
    r = admin_client.post("/admin/velopack/999/delete", follow_redirects=False)
    assert r.status_code == 303


def test_trang_hien_nut_xoa_chi_cho_ban_tat(admin_client):
    _release_with_files("1.9.1", ["a.nupkg"])
    _release_with_files("1.9.2", ["b.nupkg"], is_active=True)
    html = admin_client.get("/admin/versions").text
    assert html.count("/delete") == 1 and "confirm(" in html


def test_trang_bao_khong_co_ban_cai(admin_client):
    _release_with_files("1.9.1", ["a.nupkg"])
    assert "không có bản cài" in admin_client.get("/admin/versions").text
    _release_with_files("1.9.2", ["b.nupkg"], setup="1.9.2_s.exe")
    assert admin_client.get("/admin/versions").text.count("không có bản cài") == 1
