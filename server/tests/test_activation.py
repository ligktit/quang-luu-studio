"""Test luồng kích hoạt & verify license."""
from app.db import SessionLocal
from app.models import License
from app.services import codegen


def _make_license(max_devices=1, status="unused", plan="standard"):
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=max_devices, status=status, plan=plan))
        db.commit()
    return code


def test_activate_success(client):
    code = _make_license()
    r = client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": "dev-fingerprint-1", "hostname": "PC1", "os": "Win11",
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["valid"] is True
    assert data["status"] == "active"
    assert data["token"]


def test_activate_invalid_code(client):
    r = client.post("/api/v1/activate", json={
        "code": "AAAA-BBBB-CCCC-DDDD-EEEE", "device_fingerprint": "dev-fingerprint-1",
    })
    assert r.status_code in (400, 404)
    assert r.json()["valid"] is False


def test_activate_unknown_code(client):
    code = codegen.generate_code()  # hợp lệ checksum nhưng chưa có trong DB
    r = client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": "dev-fingerprint-1",
    })
    assert r.status_code == 404
    assert r.json()["status"] == "invalid"


def test_device_limit(client):
    code = _make_license(max_devices=1)
    client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"})
    r = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-bbbbbb"})
    assert r.status_code == 409
    assert r.json()["status"] == "device_limit"


def test_reactivate_same_device_ok(client):
    code = _make_license(max_devices=1)
    client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"})
    r = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"})
    assert r.status_code == 200
    assert r.json()["valid"] is True


def test_revoked_license(client):
    code = _make_license(status="revoked")
    r = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"})
    assert r.status_code == 403
    assert r.json()["status"] == "revoked"


def test_verify_with_token(client):
    code = _make_license()
    act = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"}).json()
    r = client.post("/api/v1/license/verify", json={
        "token": act["token"], "device_fingerprint": "device-aaaaaa",
    })
    assert r.status_code == 200
    assert r.json()["valid"] is True


def test_activate_default_plan_standard(client):
    code = _make_license()
    r = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"})
    assert r.status_code == 200
    assert r.json()["plan"] == "standard"


def test_activate_premium_plan_in_response_and_token(client):
    import jwt

    from app.security import license_public_key_pem

    code = _make_license(plan="premium")
    r = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"})
    assert r.status_code == 200
    data = r.json()
    # plan có trong response
    assert data["plan"] == "premium"
    # plan có trong JWT claim (để client biết tier khi offline), ký RS256 để
    # client tự xác minh được bằng public key nhúng sẵn.
    claims = jwt.decode(data["token"], license_public_key_pem(), algorithms=["RS256"])
    assert claims["plan"] == "premium"
    # verify cũng giữ plan
    v = client.post("/api/v1/license/verify", json={
        "token": data["token"], "device_fingerprint": "device-aaaaaa",
    })
    assert v.status_code == 200
    assert v.json()["plan"] == "premium"


def test_verify_token_wrong_device_strict_for_new_clients(client):
    """
    Client MỚI (có gửi legacy_fingerprint) chịu quy tắc chặt: token phải thuộc
    đúng máy này hoặc đúng danh tính cũ mà máy tự tính lại được từ phần cứng.
    """
    code = _make_license()
    act = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"}).json()
    r = client.post("/api/v1/license/verify", json={
        "token": act["token"], "device_fingerprint": "device-otherxx",
        "legacy_fingerprint": "device-khac-hoan-toan",
    })
    assert r.status_code == 403


def test_verify_token_migrates_for_old_clients(client):
    """
    Client CŨ (≤1.6.2) không biết gửi legacy_fingerprint. Với nó, claim `fp`
    trong token là bằng chứng duy nhất về danh tính cũ, nên fingerprint lệch
    được hiểu là "máy này vừa đổi fingerprint" chứ không phải "máy khác".

    Đây là nhượng bộ CÓ CHỦ ĐÍCH để đội hình đang chạy không bị đá ra trước khi
    bản 1.6.3 kịp phát hành — đổi lại, ai chép activation.json sang máy khác thì
    chuyển được giấy phép. Nhánh này tự vô hiệu với từng máy ngay khi máy đó cập
    nhật, và sẽ xoá hẳn khi /admin/devices không còn bản ≤1.6.2.
    """
    code = _make_license()
    act = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"}).json()
    r = client.post("/api/v1/license/verify", json={
        "token": act["token"], "device_fingerprint": "device-otherxx",
    })
    assert r.status_code == 200, r.text
