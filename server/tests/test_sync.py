"""Test Cloud Sync (Premium): round-trip PUT/GET, từ chối token sai thiết bị."""
from app.db import SessionLocal
from app.models import License
from app.services import codegen

FP = "device-aaaaaa"


def _make_license(plan="premium", max_devices=1, status="unused"):
    code = codegen.generate_code()
    with SessionLocal() as db:
        db.add(License(code=code, max_devices=max_devices, status=status, plan=plan))
        db.commit()
    return code


def _activate(client, code, fp=FP):
    return client.post("/api/v1/activate", json={
        "code": code, "device_fingerprint": fp,
    }).json()


def test_put_then_get_roundtrip(client):
    code = _make_license()
    token = _activate(client, code)["token"]

    payload = '{"songs": [{"id": 1, "url": "https://youtu.be/abc"}]}'
    r = client.put("/api/v1/sync/songs", json={
        "token": token, "device_fingerprint": FP,
        "data": payload, "updated_at": 1000.0,
    })
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["version"] == 1

    g = client.post("/api/v1/sync/songs/get", json={
        "token": token, "device_fingerprint": FP,
    })
    assert g.status_code == 200, g.text
    body = g.json()
    assert body["exists"] is True
    assert body["data"] == payload
    assert body["version"] == 1


def test_put_increments_version_last_write_wins(client):
    code = _make_license()
    token = _activate(client, code)["token"]

    client.put("/api/v1/sync/songs", json={
        "token": token, "device_fingerprint": FP, "data": "v1", "updated_at": 1000.0,
    })
    r2 = client.put("/api/v1/sync/songs", json={
        "token": token, "device_fingerprint": FP, "data": "v2", "updated_at": 2000.0,
    })
    assert r2.json()["version"] == 2

    # PUT cũ hơn (updated_at nhỏ hơn) bị bỏ qua → stale, version giữ nguyên.
    r3 = client.put("/api/v1/sync/songs", json={
        "token": token, "device_fingerprint": FP, "data": "v0", "updated_at": 500.0,
    })
    assert r3.json()["stale"] is True
    assert r3.json()["version"] == 2

    g = client.post("/api/v1/sync/songs/get", json={
        "token": token, "device_fingerprint": FP,
    })
    assert g.json()["data"] == "v2"


def test_get_missing_blob_returns_exists_false(client):
    code = _make_license()
    token = _activate(client, code)["token"]
    g = client.post("/api/v1/sync/tones/get", json={
        "token": token, "device_fingerprint": FP,
    })
    assert g.status_code == 200
    assert g.json()["exists"] is False


def test_put_wrong_device_rejected(client):
    code = _make_license()
    token = _activate(client, code)["token"]
    r = client.put("/api/v1/sync/songs", json={
        "token": token, "device_fingerprint": "device-otherxx",
        "data": "x", "updated_at": 1.0,
    })
    assert r.status_code == 403


def test_get_wrong_device_rejected(client):
    code = _make_license()
    token = _activate(client, code)["token"]
    client.put("/api/v1/sync/songs", json={
        "token": token, "device_fingerprint": FP, "data": "x", "updated_at": 1.0,
    })
    g = client.post("/api/v1/sync/songs/get", json={
        "token": token, "device_fingerprint": "device-otherxx",
    })
    assert g.status_code == 403


def test_invalid_kind_rejected(client):
    code = _make_license()
    token = _activate(client, code)["token"]
    r = client.put("/api/v1/sync/bogus", json={
        "token": token, "device_fingerprint": FP, "data": "x", "updated_at": 1.0,
    })
    assert r.status_code == 400


def test_invalid_token_rejected(client):
    r = client.put("/api/v1/sync/songs", json={
        "token": "not.a.jwt", "device_fingerprint": FP, "data": "x", "updated_at": 1.0,
    })
    assert r.status_code == 401


def test_two_devices_same_license_share_blob(client):
    """Mô phỏng 2 máy cùng mã Premium: máy A PUT, máy B GET thấy dữ liệu."""
    code = _make_license(max_devices=2)
    token_a = _activate(client, code, fp="device-aaaaaa")["token"]
    token_b = _activate(client, code, fp="device-bbbbbb")["token"]

    client.put("/api/v1/sync/songs", json={
        "token": token_a, "device_fingerprint": "device-aaaaaa",
        "data": "from-A", "updated_at": 1000.0,
    })
    g = client.post("/api/v1/sync/songs/get", json={
        "token": token_b, "device_fingerprint": "device-bbbbbb",
    })
    assert g.json()["data"] == "from-A"
