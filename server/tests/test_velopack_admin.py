from unittest.mock import patch

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
    imp.assert_called_once_with(rows[0].id)


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
