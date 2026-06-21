"""Test luồng kích hoạt & verify license."""
from app.db import SessionLocal
from app.models import License
from app.services import codegen


def _make_license(max_devices=1, status="unused"):
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=max_devices, status=status))
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


def test_verify_token_wrong_device(client):
    code = _make_license()
    act = client.post("/api/v1/activate", json={"code": code, "device_fingerprint": "device-aaaaaa"}).json()
    r = client.post("/api/v1/license/verify", json={
        "token": act["token"], "device_fingerprint": "device-otherxx",
    })
    assert r.status_code == 403
