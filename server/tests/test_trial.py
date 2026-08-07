"""Test bản dùng thử neo theo device fingerprint."""
from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import TrialGrant

FP = "trial-device-0001"


def test_first_request_grants_trial(client):
    r = client.post("/api/v1/trial/start", json={"device_fingerprint": FP, "hostname": "PC1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["allowed"] is True
    assert body["days_remaining"] == 3.0
    assert body["started_at"] > 0


def test_second_request_returns_same_start(client):
    """Máy xin lần hai không được cấp mốc mới — đây là chỗ chặn reset dùng thử."""
    first = client.post("/api/v1/trial/start", json={"device_fingerprint": FP}).json()
    second = client.post("/api/v1/trial/start", json={"device_fingerprint": FP}).json()
    assert second["allowed"] is True
    assert second["started_at"] == first["started_at"]
    assert second["days_remaining"] <= first["days_remaining"]


def test_expired_trial_is_refused(client):
    client.post("/api/v1/trial/start", json={"device_fingerprint": FP})
    # Đẩy mốc bắt đầu về 10 ngày trước
    with SessionLocal() as db:
        grant = db.query(TrialGrant).filter_by(fingerprint=FP).one()
        grant.started_at = datetime.now(timezone.utc) - timedelta(days=10)
        db.commit()

    body = client.post("/api/v1/trial/start", json={"device_fingerprint": FP}).json()
    assert body["allowed"] is False
    assert body["days_remaining"] == 0.0


def test_different_machine_gets_its_own_trial(client):
    client.post("/api/v1/trial/start", json={"device_fingerprint": FP})
    other = client.post("/api/v1/trial/start", json={"device_fingerprint": "another-device-02"}).json()
    assert other["allowed"] is True
    assert other["days_remaining"] == 3.0
