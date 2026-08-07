"""Cloud Sync (Premium): lưu/đồng bộ blob dữ liệu người dùng theo license.

Xác thực bằng license token (decode_license_token) — fp phải khớp thiết bị.
Last-write-wins theo updated_at. Server không hiểu nội dung blob.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import SyncBlob
from app.schemas import SyncGetRequest, SyncPutRequest, SyncResponse
from app.security import decode_license_token, limiter
from app.services import licensing

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])

# Các loại blob được phép đồng bộ. Khớp KIND_FILES bên client.
ALLOWED_KINDS = {"songs", "timelines", "tones", "scores"}


def _error(message: str, http_status: int) -> JSONResponse:
    body = SyncResponse(ok=False, message=message).model_dump(mode="json")
    return JSONResponse(status_code=http_status, content=body)


def _authorize(token: str | None, fingerprint: str, db: Session) -> tuple[str | None, JSONResponse | None]:
    """
    Xác thực BẮT BUỘC bằng token đã ký, ràng đúng máy, rồi kiểm lại license
    trong DB. Trả (license_code, lỗi).

    Không có fallback bằng mã thô: mã kích hoạt là chuỗi ngắn người dùng đọc
    được và hay bị chụp màn hình gửi cho nhau — ai biết mã của người khác cũng
    đọc/ghi được thư viện của họ.

    Kiểm DB ở đây (chứ không chỉ tin claim trong token) để lệnh thu hồi hoặc hạ
    gói có hiệu lực NGAY, thay vì phải chờ token cũ hết hạn grace.
    """
    if not token:
        return None, _error("Thiếu license token. Hãy mở lại app để kích hoạt lại.", 401)
    claims = decode_license_token(token)
    if claims is None:
        return None, _error("Token không hợp lệ hoặc hết hạn.", 401)
    if claims.get("fp") != fingerprint:
        return None, _error("Token không khớp thiết bị.", 403)
    code = claims.get("code")
    if not code:
        return None, _error("Token thiếu mã license.", 401)

    lic = licensing.get_license(db, code)
    if lic is None:
        return None, _error("Mã không tồn tại.", 404)
    if lic.status == "revoked":
        return None, _error("Mã đã bị thu hồi.", 403)
    if licensing.is_expired(lic):
        return None, _error("Mã đã hết hạn.", 403)
    if (lic.plan or "standard").lower() != "premium":
        return None, _error("Đồng bộ đám mây là tính năng của gói Premium.", 403)

    device = next((d for d in lic.devices if d.fingerprint == fingerprint), None)
    if device is None or device.revoked:
        return None, _error("Thiết bị chưa được kích hoạt hoặc đã bị thu hồi.", 403)

    return lic.code, None


def _to_epoch(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@router.put("/{kind}", response_model=SyncResponse)
@limiter.limit(settings.rate_limit_verify)
def put_blob(kind: str, request: Request, payload: SyncPutRequest, db: Session = Depends(get_db)):
    if kind not in ALLOWED_KINDS:
        return _error(f"Loại đồng bộ không hợp lệ: {kind}", 400)

    code, err = _authorize(payload.token, payload.device_fingerprint, db)
    if err is not None:
        return err

    incoming_ts = _to_epoch(payload.updated_at)
    incoming_dt = (
        datetime.fromtimestamp(incoming_ts, tz=timezone.utc)
        if incoming_ts is not None
        else datetime.now(timezone.utc)
    )

    blob = (
        db.query(SyncBlob)
        .filter(SyncBlob.license_code == code, SyncBlob.kind == kind)
        .one_or_none()
    )

    if blob is None:
        blob = SyncBlob(
            license_code=code,
            kind=kind,
            data=payload.data,
            version=1,
            updated_at=incoming_dt,
        )
        db.add(blob)
        db.commit()
        db.refresh(blob)
        return SyncResponse(
            ok=True, kind=kind, exists=True,
            version=blob.version, updated_at=blob.updated_at,
        )

    # Last-write-wins: chỉ ghi khi bản client mới hơn (hoặc không rõ thời gian).
    existing = blob.updated_at
    if existing is not None and existing.tzinfo is None:
        existing = existing.replace(tzinfo=timezone.utc)
    if incoming_ts is not None and existing is not None and incoming_dt < existing:
        return SyncResponse(
            ok=True, kind=kind, exists=True, stale=True,
            version=blob.version, updated_at=blob.updated_at,
            message="Server có bản mới hơn; PUT bị bỏ qua.",
        )

    blob.data = payload.data
    blob.version += 1
    blob.updated_at = incoming_dt
    db.commit()
    db.refresh(blob)
    return SyncResponse(
        ok=True, kind=kind, exists=True,
        version=blob.version, updated_at=blob.updated_at,
    )


def _get_blob(kind: str, code: str | None, db: Session) -> SyncResponse:
    blob = (
        db.query(SyncBlob)
        .filter(SyncBlob.license_code == code, SyncBlob.kind == kind)
        .one_or_none()
    )
    if blob is None:
        return SyncResponse(ok=True, kind=kind, exists=False)
    return SyncResponse(
        ok=True, kind=kind, exists=True,
        data=blob.data, version=blob.version, updated_at=blob.updated_at,
    )


@router.post("/{kind}/get", response_model=SyncResponse)
@limiter.limit(settings.rate_limit_verify)
def get_blob_post(kind: str, request: Request, payload: SyncGetRequest, db: Session = Depends(get_db)):
    """
    Lấy blob. Chỉ có đường POST: biến thể GET cũ nhận token qua query string,
    mà query string thì nằm sẵn trong log của nginx và mọi proxy trung gian.
    """
    if kind not in ALLOWED_KINDS:
        return _error(f"Loại đồng bộ không hợp lệ: {kind}", 400)
    code, err = _authorize(payload.token, payload.device_fingerprint, db)
    if err is not None:
        return err
    return _get_blob(kind, code, db)
