"""Test updates check + crash dedupe + admin smoke."""
import io

from app.db import SessionLocal
from app.models import AppVersion, CrashReport


def _add_version(version, rollout=100, active=True, channel="stable"):
    with SessionLocal() as db:
        db.add(AppVersion(
            version=version, channel=channel, filename=f"{version}.exe",
            sha256="0" * 64, size_bytes=1234, rollout_percent=rollout, is_active=active,
        ))
        db.commit()


def test_update_available(client):
    _add_version("1.6.0")
    r = client.get("/api/v1/updates/check", params={"version": "1.5.1", "fingerprint": "fp"})
    assert r.status_code == 200
    data = r.json()
    assert data["update_available"] is True
    assert data["version"] == "1.6.0"
    assert data["download_url"].endswith("/api/v1/updates/download/1.6.0")


def test_no_update_when_same(client):
    _add_version("1.5.1")
    r = client.get("/api/v1/updates/check", params={"version": "1.5.1", "fingerprint": "fp"})
    assert r.json()["update_available"] is False


def test_rollout_excludes_some(client):
    # rollout 0% → không ai nhận
    _add_version("2.0.0", rollout=0)
    r = client.get("/api/v1/updates/check", params={"version": "1.0.0", "fingerprint": "any-fp"})
    assert r.json()["update_available"] is False


def test_crash_dedupe(client):
    body = {"app_version": "1.5.1", "traceback": "Traceback X\nValueError", "device_fingerprint": "fp"}
    r1 = client.post("/api/v1/crash", json=body)
    r2 = client.post("/api/v1/crash", json=body)
    assert r1.json()["report_id"] == r2.json()["report_id"]
    with SessionLocal() as db:
        rep = db.get(CrashReport, r1.json()["report_id"])
        assert rep.count == 2


def test_crash_distinct(client):
    client.post("/api/v1/crash", json={"app_version": "1.5.1", "traceback": "Err A"})
    client.post("/api/v1/crash", json={"app_version": "1.5.1", "traceback": "Err B"})
    with SessionLocal() as db:
        assert db.query(CrashReport).count() == 2


def test_admin_requires_login(client):
    r = client.get("/admin/users", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/admin/login"


def test_admin_login_and_generate(admin_client):
    r = admin_client.post("/admin/licenses/generate", data={"count": 3, "max_devices": 1, "plan": "standard"}, follow_redirects=False)
    assert r.status_code == 303
    from app.models import License
    with SessionLocal() as db:
        assert db.query(License).count() == 3
