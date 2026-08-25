"""
Logic kích hoạt & xác thực license — tách khỏi router để dễ test.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Device, License, TrialGrant
from app.security import issue_license_token
from app.services import codegen

log = logging.getLogger(__name__)


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


def _legacy_set(legacy, fingerprint: str) -> set[str]:
    """Chuẩn hoá danh sách fingerprint cũ có thể có (bỏ rỗng và bỏ chính nó)."""
    if legacy is None:
        return set()
    values = {legacy} if isinstance(legacy, str) else set(legacy)
    return {v for v in values if v and v != fingerprint}


def find_device(
    db: Session, lic: License, fingerprint: str, legacy=None
) -> Device | None:
    """
    Tìm bản ghi thiết bị của MỘT máy vật lý, chấp nhận cả fingerprint cũ.

    Client ≤1.6.2 tính fingerprint từ MachineGuid + MAC + tên máy + CPU; ba thành
    phần sau đổi theo card mạng/VPN/đổi tên máy, nên cùng một máy sinh ra nhiều
    fingerprint khác nhau → chiếm hết slot → "đã đạt giới hạn thiết bị". Client
    mới chỉ dùng MachineGuid và gửi kèm giá trị cũ để server nối lại hai danh
    tính đó.

    `legacy` nhận một chuỗi hoặc nhiều chuỗi. Nguồn của chúng:
      - `legacy_fingerprint` client mới gửi kèm (công thức cũ tính lại tại chỗ);
      - claim `fp` trong token client đang giữ — đây là **chữ ký của chính server**
        xác nhận máy này từng được cấp phép dưới danh tính đó, nên dùng được cả
        với client CŨ chưa cập nhật (chúng không biết gửi legacy_fingerprint).
      - Máy drift nhiều lần (A→B→C) sẽ có token mang A trong khi legacy tính ra
        B; nhận cả hai nên vẫn nối được.

    Ba tình huống:
      1. Chỉ có bản ghi cũ → ĐỔI TÊN tại chỗ sang fingerprint mới (không tốn slot).
      2. Có cả hai → cùng một máy có hai bản ghi (di sản của drift) → gộp, bỏ cái cũ.
      3. Bản ghi cũ đang bị chặn → GIỮ NGUYÊN trạng thái chặn, không di trú.
         Nếu không, ai bị cấm chỉ cần cập nhật app là né được lệnh cấm.
    """
    device = next((d for d in lic.devices if d.fingerprint == fingerprint), None)
    olds = _legacy_set(legacy, fingerprint)
    legacy_dev = next((d for d in lic.devices if d.fingerprint in olds), None) if olds else None

    if legacy_dev is None:
        return device

    if legacy_dev.revoked:
        # Lệnh cấm đi theo máy, không né được bằng cách đổi cách tính fingerprint.
        return device if (device is not None and device.revoked) else legacy_dev

    if device is None:
        log.info("Di trú fingerprint v1→v2 cho device %s (license %s)", legacy_dev.id, lic.code)
        legacy_dev.fingerprint = fingerprint
        return legacy_dev

    if legacy_dev is not device:
        log.info("Gộp 2 bản ghi cùng máy: bỏ device %s, giữ %s (license %s)",
                 legacy_dev.id, device.id, lic.code)
        db.delete(legacy_dev)
    return device


def activate(
    db: Session,
    code: str,
    fingerprint: str,
    hostname: str | None = None,
    os: str | None = None,
    app_version: str | None = None,
    legacy_fingerprint: str | None = None,
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

    # Tìm device đã ràng (theo fingerprint, chấp nhận cả giá trị cũ)
    device = find_device(db, lic, fingerprint, legacy_fingerprint)
    if device is None:
        active = lic.active_devices
        if len(active) >= lic.max_devices:
            raise LicenseError(
                f"Mã đã đạt giới hạn {lic.max_devices} thiết bị. "
                f"Liên hệ hỗ trợ và đọc mã máy: {fingerprint[:8]}",
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
            raise LicenseError(
                f"Thiết bị này đã bị chặn. Liên hệ hỗ trợ và đọc mã máy: {fingerprint[:8]}",
                status="revoked",
                http_status=403,
            )
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


def _find_trial_grant(db: Session, fingerprint: str, legacy: str | None) -> TrialGrant | None:
    """
    Suất dùng thử của một máy, nối được cả danh tính cũ.

    Bỏ qua bước này thì mỗi máy cập nhật app sẽ có fingerprint mới → server coi
    là máy chưa từng dùng thử → tặng thêm 3 ngày nữa. Khi có cả hai bản ghi thì
    giữ mốc SỚM NHẤT, để việc đổi cách tính fingerprint không kéo dài hạn.
    """
    grant = db.scalar(select(TrialGrant).where(TrialGrant.fingerprint == fingerprint))
    if not legacy or legacy == fingerprint:
        return grant

    legacy_grant = db.scalar(select(TrialGrant).where(TrialGrant.fingerprint == legacy))
    if legacy_grant is None:
        return grant

    if grant is None:
        legacy_grant.fingerprint = fingerprint
        log.info("Di trú suất dùng thử v1→v2 (grant %s)", legacy_grant.id)
        return legacy_grant

    if legacy_grant is not grant:
        old = _aware(legacy_grant.started_at)
        cur = _aware(grant.started_at)
        if old is not None and (cur is None or old < cur):
            grant.started_at = legacy_grant.started_at
        db.delete(legacy_grant)
    return grant


def start_trial(
    db: Session,
    fingerprint: str,
    hostname: str | None = None,
    os: str | None = None,
    app_version: str | None = None,
    legacy_fingerprint: str | None = None,
) -> dict:
    """
    Cấp (hoặc trả lại) bản dùng thử của MỘT máy. Trả dict cho TrialResponse.

    Máy đã từng dùng thử luôn nhận lại đúng started_at cũ — kể cả khi người dùng
    đã xoá sạch dữ liệu dưới máy — nên hạn dùng thử không reset được.
    """
    now = datetime.now(timezone.utc)
    grant = _find_trial_grant(db, fingerprint, legacy_fingerprint)

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


def verify(db: Session, code: str, fingerprint: str, app_version: str | None = None,
           legacy_fingerprint: str | None = None) -> dict:
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

    device = find_device(db, lic, fingerprint, legacy_fingerprint)
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


def authorize_device(
    db: Session,
    token: str | None,
    fingerprint: str,
    *,
    require_premium: bool = True,
) -> tuple[str | None, str | None, int]:
    """
    Xác thực BẮT BUỘC bằng token đã ký, ràng đúng máy, rồi kiểm lại license
    trong DB. Trả (license_code, thông_báo_lỗi, http_status).

    Không có fallback bằng mã thô: mã kích hoạt là chuỗi ngắn người dùng đọc
    được và hay bị chụp màn hình gửi cho nhau — ai biết mã của người khác cũng
    đọc/ghi được thư viện của họ.

    Kiểm DB ở đây (chứ không chỉ tin claim trong token) để lệnh thu hồi hoặc hạ
    gói có hiệu lực NGAY, thay vì phải chờ token cũ hết hạn grace.

    require_premium=True  → dùng cho Cloud Sync (dữ liệu riêng tư, gói Premium).
    require_premium=False → dùng cho thư viện tone cộng đồng: mọi máy đã kích
        hoạt đều đọc/ghi được, vì càng nhiều máy đóng góp thì dữ liệu càng dày.
    """
    # Import trễ: app.security nạp khoá ký, không nên kéo vào lúc import module.
    from app.security import decode_license_token

    if not token:
        return None, "Thiếu license token. Hãy mở lại app để kích hoạt lại.", 401
    claims = decode_license_token(token)
    if claims is None:
        return None, "Token không hợp lệ hoặc hết hạn.", 401
    if claims.get("fp") != fingerprint:
        return None, "Token không khớp thiết bị.", 403
    code = claims.get("code")
    if not code:
        return None, "Token thiếu mã license.", 401

    lic = get_license(db, code)
    if lic is None:
        return None, "Mã không tồn tại.", 404
    if lic.status == "revoked":
        return None, "Mã đã bị thu hồi.", 403
    if is_expired(lic):
        return None, "Mã đã hết hạn.", 403
    if require_premium and (lic.plan or "standard").lower() != "premium":
        return None, "Đồng bộ đám mây là tính năng của gói Premium.", 403

    device = next((d for d in lic.devices if d.fingerprint == fingerprint), None)
    if device is None or device.revoked:
        return None, "Thiết bị chưa được kích hoạt hoặc đã bị thu hồi.", 403

    return lic.code, None, 200
