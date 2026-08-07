"""
Logic kích hoạt & xác thực license — tách khỏi router để dễ test.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Device, License, TrialGrant
from app.security import issue_license_token
from app.services import codegen


class LicenseError(Exception):
    """Lỗi nghiệp vụ kích hoạt — kèm status code gợi ý."""

    def __init__(self, message: str, status: str = "invalid", http_status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status
        self.http_status = http_status


def _aware(dt: datetime | None) -> datetime | None:
    """Đảm bảo datetime có tzinfo (Postgres trả aware, SQLite test có thể naive)."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_remaining(expires_at: datetime | None) -> int | None:
    expires_at = _aware(expires_at)
    if expires_at is None:
        return None
    delta = expires_at - datetime.now(timezone.utc)
    return max(0, delta.days)


def is_expired(lic: License) -> bool:
    exp = _aware(lic.expires_at)
    return exp is not None and exp < datetime.now(timezone.utc)


def get_license(db: Session, code: str) -> License | None:
    code = code.strip().upper()
    return db.scalar(select(License).where(License.code == code))


def activate(
    db: Session,
    code: str,
    fingerprint: str,
    hostname: str | None = None,
    os: str | None = None,
    app_version: str | None = None,
) -> dict:
    """
    Kích hoạt mã + ràng device. Trả dict cho LicenseResponse.
    Raise LicenseError nếu thất bại.
    """
    code = code.strip().upper()

    if not codegen.is_valid_code(code):
        raise LicenseError("Mã kích hoạt không hợp lệ.", status="invalid", http_status=400)

    lic = get_license(db, code)
    if lic is None:
        raise LicenseError("Mã không tồn tại trong hệ thống.", status="invalid", http_status=404)

    if lic.status == "revoked":
        raise LicenseError("Mã đã bị thu hồi.", status="revoked", http_status=403)

    if is_expired(lic):
        lic.status = "expired"
        db.commit()
        raise LicenseError("Mã đã hết hạn.", status="expired", http_status=403)

    # Lần đầu kích hoạt → đặt activated_at + expires_at
    now = datetime.now(timezone.utc)
    if lic.activated_at is None:
        lic.activated_at = now
        if lic.expires_at is None and settings.license_duration_days > 0:
            lic.expires_at = now + timedelta(days=settings.license_duration_days)
    lic.status = "active"

    # Tìm device đã ràng (theo fingerprint)
    device = next((d for d in lic.devices if d.fingerprint == fingerprint), None)
    if device is None:
        active = lic.active_devices
        if len(active) >= lic.max_devices:
            raise LicenseError(
                f"Mã đã đạt giới hạn {lic.max_devices} thiết bị. "
                "Liên hệ quản trị để reset thiết bị.",
                status="device_limit",
                http_status=409,
            )
        device = Device(
            license_id=lic.id,
            fingerprint=fingerprint,
            hostname=hostname,
            os=os,
            app_version=app_version,
        )
        db.add(device)
    else:
        if device.revoked:
            raise LicenseError("Thiết bị này đã bị thu hồi quyền.", status="revoked", http_status=403)
        device.hostname = hostname or device.hostname
        device.os = os or device.os
        device.app_version = app_version or device.app_version

    device.last_seen = now
    device.last_check_in = now
    db.commit()

    token = issue_license_token(lic.code, fingerprint, _aware(lic.expires_at), lic.plan)
    return {
        "valid": True,
        "status": "active",
        "token": token,
        "plan": lic.plan,
        "days_remaining": _days_remaining(lic.expires_at),
        "expires_at": _aware(lic.expires_at),
        "message": "Kích hoạt thành công.",
    }


def start_trial(
    db: Session,
    fingerprint: str,
    hostname: str | None = None,
    os: str | None = None,
    app_version: str | None = None,
) -> dict:
    """
    Cấp (hoặc trả lại) bản dùng thử của MỘT máy. Trả dict cho TrialResponse.

    Máy đã từng dùng thử luôn nhận lại đúng started_at cũ — kể cả khi người dùng
    đã xoá sạch dữ liệu dưới máy — nên hạn dùng thử không reset được.
    """
    now = datetime.now(timezone.utc)
    grant = db.scalar(select(TrialGrant).where(TrialGrant.fingerprint == fingerprint))

    if grant is None:
        grant = TrialGrant(
            fingerprint=fingerprint,
            hostname=hostname,
            os=os,
            app_version=app_version,
            started_at=now,
            last_seen=now,
        )
        db.add(grant)
        db.commit()
        return {
            "allowed": True,
            "started_at": now.timestamp(),
            "days_remaining": float(settings.trial_days),
            "message": f"Bắt đầu dùng thử {settings.trial_days} ngày.",
        }

    grant.last_seen = now
    grant.hostname = hostname or grant.hostname
    grant.os = os or grant.os
    grant.app_version = app_version or grant.app_version
    db.commit()

    started = _aware(grant.started_at) or now
    elapsed_days = (now - started).total_seconds() / 86400
    remaining = settings.trial_days - elapsed_days
    if remaining <= 0:
        return {
            "allowed": False,
            "started_at": started.timestamp(),
            "days_remaining": 0.0,
            "message": "Máy này đã dùng hết thời gian dùng thử.",
        }
    return {
        "allowed": True,
        "started_at": started.timestamp(),
        "days_remaining": remaining,
        "message": "Đang trong thời gian dùng thử.",
    }


def verify(db: Session, code: str, fingerprint: str, app_version: str | None = None) -> dict:
    """
    Check-in định kỳ: xác nhận mã còn hiệu lực + device còn được phép.
    Trả dict cho LicenseResponse (kèm token mới để gia hạn grace).
    """
    code = code.strip().upper()
    lic = get_license(db, code)
    if lic is None:
        raise LicenseError("Mã không tồn tại.", status="invalid", http_status=404)
    if lic.status == "revoked":
        raise LicenseError("Mã đã bị thu hồi.", status="revoked", http_status=403)
    if is_expired(lic):
        lic.status = "expired"
        db.commit()
        raise LicenseError("Mã đã hết hạn.", status="expired", http_status=403)

    device = next((d for d in lic.devices if d.fingerprint == fingerprint), None)
    if device is None:
        raise LicenseError("Thiết bị chưa được kích hoạt.", status="not_activated", http_status=403)
    if device.revoked:
        raise LicenseError("Thiết bị đã bị thu hồi quyền.", status="revoked", http_status=403)

    now = datetime.now(timezone.utc)
    device.last_seen = now
    device.last_check_in = now
    if app_version:
        device.app_version = app_version
    db.commit()

    token = issue_license_token(lic.code, fingerprint, _aware(lic.expires_at), lic.plan)
    return {
        "valid": True,
        "status": "active",
        "token": token,
        "plan": lic.plan,
        "days_remaining": _days_remaining(lic.expires_at),
        "expires_at": _aware(lic.expires_at),
        "message": "OK",
    }
