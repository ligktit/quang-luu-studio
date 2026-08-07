"""
Test các chỗ đã siết: token phải ký RS256, Cloud Sync bắt buộc token, và mọi
lệnh thu hồi/hạ gói có hiệu lực ngay chứ không chờ token cũ hết hạn.
"""
import jwt
from app.db import SessionLocal
from app.models import License
from app.security import license_public_key_pem
from app.services import codegen

FP = "hardening-device-01"


def _make_license(plan="premium", max_devices=1):
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=max_devices, status="unused", plan=plan))
        db.commit()
    return code


def _activate(client, code, fp=FP):
    return client.post("/api/v1/activate", json={"code": code, "device_fingerprint": fp}).json()


def _set_status(code, status):
    with SessionLocal() as db:
        lic = db.query(License).filter_by(code=code).one()
        lic.status = status
        db.commit()


def _set_plan(code, plan):
    with SessionLocal() as db:
        lic = db.query(License).filter_by(code=code).one()
        lic.plan = plan
        db.commit()


# --- Chữ ký token ---

def test_token_is_signed_rs256(client):
    token = _activate(client, _make_license())["token"]
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "RS256"
    # Xác minh được bằng public key → client cũng làm được y hệt.
    claims = jwt.decode(token, license_public_key_pem(), algorithms=["RS256"])
    assert claims["fp"] == FP


def test_legacy_hs256_token_still_readable(client):
    """
    Máy chưa cập nhật gửi token HS256 cũ → server vẫn đọc được nhờ LICENSE_SECRET
    và cấp lại token RS256. Đây là đường nâng cấp êm cho máy đang chạy; xoá
    LICENSE_SECRET khỏi .env sẽ chặn đường này (có chủ đích, sau khi mọi máy đã lên).
    """
    from app.config import settings

    code = _make_license()
    _activate(client, code)  # tạo device trước

    legacy = jwt.encode(
        {"code": code, "fp": FP, "plan": "standard", "exp": 9999999999},
        settings.license_secret,
        algorithm="HS256",
    )
    r = client.post("/api/v1/license/verify", json={"token": legacy, "device_fingerprint": FP})
    assert r.status_code == 200, r.text
    # Token trả về phải là RS256 — máy đó được nâng cấp ngay trong lần check-in này.
    assert jwt.get_unverified_header(r.json()["token"])["alg"] == "RS256"


def test_token_signed_with_wrong_key_is_rejected(client):
    """Token tự ký bằng khoá khác không qua được /license/verify."""
    _activate(client, _make_license())
    forged = jwt.encode({"code": "AB12-CD34-EF56-GH78-XY90", "fp": FP, "plan": "premium"},
                        "khoa-bia-dat", algorithm="HS256")
    r = client.post("/api/v1/license/verify", json={
        "token": forged, "device_fingerprint": FP,
    })
    assert r.status_code == 401


# --- Cloud Sync ---

def test_sync_requires_token(client):
    """Biết mã license thôi thì không đọc được dữ liệu của người khác."""
    code = _make_license()
    _activate(client, code)
    r = client.post("/api/v1/sync/songs/get", json={
        "code": code, "device_fingerprint": FP,
    })
    assert r.status_code == 401


def test_sync_refuses_standard_plan(client):
    """Gói Standard bị chặn ở server, không chỉ ẩn nút trong app."""
    code = _make_license(plan="standard")
    token = _activate(client, code)["token"]
    r = client.put("/api/v1/sync/songs", json={
        "token": token, "device_fingerprint": FP, "data": "[]", "updated_at": 1000.0,
    })
    assert r.status_code == 403


def test_sync_stops_right_after_revoke(client):
    """Thu hồi có hiệu lực ngay, không đợi token cũ hết grace."""
    code = _make_license()
    token = _activate(client, code)["token"]
    ok = client.put("/api/v1/sync/songs", json={
        "token": token, "device_fingerprint": FP, "data": "[]", "updated_at": 1000.0,
    })
    assert ok.status_code == 200

    _set_status(code, "revoked")
    after = client.put("/api/v1/sync/songs", json={
        "token": token, "device_fingerprint": FP, "data": "[]", "updated_at": 2000.0,
    })
    assert after.status_code == 403


def test_sync_stops_right_after_downgrade(client):
    code = _make_license()
    token = _activate(client, code)["token"]
    _set_plan(code, "standard")
    r = client.post("/api/v1/sync/songs/get", json={"token": token, "device_fingerprint": FP})
    assert r.status_code == 403


def test_sync_get_over_query_string_is_gone(client):
    """Đường GET cũ đẩy token vào query string (nằm trong log nginx) — đã bỏ."""
    token = _activate(client, _make_license())["token"]
    r = client.get(f"/api/v1/sync/songs?token={token}&device_fingerprint={FP}")
    assert r.status_code == 405


def test_verify_reflects_revoke_immediately(client):
    code = _make_license()
    token = _activate(client, code)["token"]
    _set_status(code, "revoked")
    r = client.post("/api/v1/license/verify", json={"token": token, "device_fingerprint": FP})
    assert r.status_code == 403
    assert r.json()["status"] == "revoked"
