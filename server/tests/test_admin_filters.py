"""
Bộ lọc theo dõi trong admin UI: trang Thiết bị, cờ chẩn đoán ở trang Mã kích
hoạt, và khối "Sức khoẻ giấy phép" ở Tổng quan.

Mục đích của những màn này là để không phải mở SQL mỗi lần khách gọi — nên test
bám vào đúng các tình huống đã gặp thật: máy bị chặn, fingerprint đổi, máy im
quá lâu, và phủ sóng phiên bản.
"""
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import Device, License
from app.services import codegen


def _license(max_devices=2, status="active"):
    code = codegen.generate_code()
    with SessionLocal() as db:
        lic = License(code=code, max_devices=max_devices, status=status, plan="standard")
        db.add(lic)
        db.commit()
        return code, lic.id


def _device(lic_id, fp, hostname="PC", version="1.6.2", revoked=False, quiet_days=0.0):
    with SessionLocal() as db:
        d = Device(
            license_id=lic_id, fingerprint=fp, hostname=hostname,
            app_version=version, revoked=revoked,
            last_check_in=datetime.now(timezone.utc) - timedelta(days=quiet_days),
        )
        db.add(d)
        db.commit()
        return d.id


# ── Trang Thiết bị ───────────────────────────────────────────────────────────

def test_devices_page_requires_admin(client):
    r = client.get("/admin/devices", follow_redirects=False)
    assert r.status_code == 303 and "/admin/login" in r.headers["location"]


def test_devices_page_lists_and_counts(admin_client):
    _, lic_id = _license()
    _device(lic_id, "fp-binh-thuong-01", hostname="PC-CHAY", quiet_days=1)
    _device(lic_id, "fp-im-lau-02", hostname="PC-IM", quiet_days=12)
    _device(lic_id, "fp-bi-chan-03", hostname="PC-CHAN", revoked=True)

    body = admin_client.get("/admin/devices").text
    for name in ("PC-CHAY", "PC-IM", "PC-CHAN"):
        assert name in body
    assert "im lâu" in body and "đã chặn" in body


def test_devices_filter_by_state(admin_client):
    _, lic_id = _license()
    _device(lic_id, "fp-chay-01", hostname="PC-CHAY", quiet_days=1)
    _device(lic_id, "fp-chan-02", hostname="PC-CHAN", revoked=True)

    blocked = admin_client.get("/admin/devices?state=blocked").text
    assert "PC-CHAN" in blocked and "PC-CHAY" not in blocked

    stale = admin_client.get("/admin/devices?state=stale").text
    assert "PC-CHAY" not in stale


def test_devices_filter_by_version(admin_client):
    """Đây là cách theo dõi bản vá đã tới bao nhiêu máy."""
    _, lic_id = _license(max_devices=5)
    _device(lic_id, "fp-cu-01", hostname="PC-CU", version="1.6.2")
    _device(lic_id, "fp-moi-02", hostname="PC-MOI", version="1.6.3")

    body = admin_client.get("/admin/devices?version=1.6.3").text
    assert "PC-MOI" in body and "PC-CU" not in body


def test_devices_search_matches_hostname_and_code(admin_client):
    code, lic_id = _license()
    _device(lic_id, "fp-tim-duoc-01", hostname="PC-TIM")
    _device(lic_id, "fp-khac-02", hostname="PC-KHAC")

    assert "PC-TIM" in admin_client.get("/admin/devices?q=pc-tim").text
    assert "PC-KHAC" not in admin_client.get("/admin/devices?q=pc-tim").text
    assert "PC-TIM" in admin_client.get(f"/admin/devices?q={code}").text


def test_devices_page_has_delete_button(admin_client):
    _, lic_id = _license()
    dev_id = _device(lic_id, "fp-go-duoc-01")
    assert f"/admin/devices/{dev_id}/delete" in admin_client.get("/admin/devices").text


# ── Cờ chẩn đoán ở trang Mã kích hoạt ────────────────────────────────────────

def test_flag_blocked(admin_client):
    code_ok, ok_id = _license()
    _device(ok_id, "fp-ok-01")
    code_bad, bad_id = _license()
    _device(bad_id, "fp-bad-01", revoked=True)

    body = admin_client.get("/admin/licenses?flag=blocked").text
    assert code_bad in body and code_ok not in body


def test_flag_drift_spots_repeated_hostname(admin_client):
    """Một tên máy có nhiều bản ghi = fingerprint đã đổi."""
    code_drift, drift_id = _license(max_devices=3)
    _device(drift_id, "fp-cu-01", hostname="DESKTOP-ABC")
    _device(drift_id, "fp-moi-02", hostname="DESKTOP-ABC")
    code_ok, ok_id = _license(max_devices=3)
    _device(ok_id, "fp-a-01", hostname="MAY-A")
    _device(ok_id, "fp-b-02", hostname="MAY-B")

    body = admin_client.get("/admin/licenses?flag=drift").text
    assert code_drift in body and code_ok not in body


def test_flag_full_and_unbound(admin_client):
    code_full, full_id = _license(max_devices=1)
    _device(full_id, "fp-full-01")
    code_free, _ = _license(max_devices=1)

    full = admin_client.get("/admin/licenses?flag=full").text
    assert code_full in full and code_free not in full

    unbound = admin_client.get("/admin/licenses?flag=unbound").text
    assert code_free in unbound and code_full not in unbound


def test_flag_stale_ignores_revoked_devices(admin_client):
    """Máy bị chặn không tính vào 'im lâu' — nếu không mọi mã đã cấm đều báo động."""
    code, lic_id = _license(max_devices=3)
    _device(lic_id, "fp-chan-01", revoked=True, quiet_days=99)
    _device(lic_id, "fp-chay-02", quiet_days=0)

    assert code not in admin_client.get("/admin/licenses?flag=stale").text


def test_license_search_and_filters_combine(admin_client):
    code, lic_id = _license(status="active")
    _device(lic_id, "fp-x-01", hostname="MAY-TIM-DUOC")
    other, _ = _license(status="unused")

    body = admin_client.get(f"/admin/licenses?q=may-tim&status=active").text
    assert code in body and other not in body


def test_flag_counts_stay_visible_after_filtering(admin_client):
    """
    Số trên các nút cờ phải đếm trên tập chưa lọc cờ — nếu không, bấm vào rồi
    số tự tụt về đúng phần đang xem và không còn dùng để theo dõi được.
    """
    _, lic_id = _license()
    _device(lic_id, "fp-chan-01", revoked=True)

    body = admin_client.get("/admin/licenses?flag=blocked").text
    assert "Có máy bị chặn: 1" in body


# ── Tổng quan ────────────────────────────────────────────────────────────────

def test_dashboard_health_block(admin_client):
    _, lic_id = _license(max_devices=3)
    _device(lic_id, "fp-cu-01", hostname="DESKTOP-XY", version="1.6.2", quiet_days=40)
    _device(lic_id, "fp-moi-02", hostname="DESKTOP-XY", version="1.6.3", quiet_days=0)
    _device(lic_id, "fp-chan-03", hostname="PC-CHAN", revoked=True)

    body = admin_client.get("/admin").text
    assert "Sức khoẻ giấy phép" in body
    assert "/admin/licenses?flag=drift" in body      # hai bản ghi cùng hostname
    assert "/admin/devices?state=blocked" in body
    assert "v1.6." in body                            # phiên bản phổ biến nhất
