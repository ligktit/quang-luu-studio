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
from app.security import limiter
from app.services import licensing

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])

# Các loại blob được phép đồng bộ. Khớp KIND_FILES bên client.
ALLOWED_KINDS = {"songs", "timelines", "tones", "scores"}


def _error(message: str, http_status: int) -> JSONResponse:
    body = SyncResponse(ok=False, message=message).model_dump(mode="json")
    return JSONResponse(status_code=http_status, content=body)


def _authorize(token: str | None, fingerprint: str, db: Session) -> tuple[str | None, JSONResponse | None]:
    """Cổng Premium của Cloud Sync — mỏng, mọi luật nằm ở licensing.authorize_device."""
    code, message, status = licensing.authorize_device(db, token, fingerprint, require_premium=True)
    if message is not None:
        return None, _error(message, status)
    return code, None


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
