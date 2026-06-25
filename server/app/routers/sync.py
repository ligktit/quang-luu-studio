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

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])

# Các loại blob được phép đồng bộ. Khớp KIND_FILES bên client.
ALLOWED_KINDS = {"songs", "timelines", "tones", "scores"}


def _error(message: str, http_status: int) -> JSONResponse:
    body = SyncResponse(ok=False, message=message).model_dump(mode="json")
    return JSONResponse(status_code=http_status, content=body)


def _resolve_code(token: str | None, code: str | None, fingerprint: str) -> tuple[str | None, JSONResponse | None]:
    """Ưu tiên token (đã ký, ràng fp). Trả (code, lỗi). code=None nếu lỗi."""
    if token:
        claims = decode_license_token(token)
        if claims is None:
            return None, _error("Token không hợp lệ hoặc hết hạn.", 401)
        if claims.get("fp") != fingerprint:
            return None, _error("Token không khớp thiết bị.", 403)
        return claims.get("code"), None
    if code:
        # Cho phép fallback code thô (giống verify) — kém an toàn hơn token.
        return code, None
    return None, _error("Thiếu mã hoặc token.", 400)


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

    code, err = _resolve_code(payload.token, payload.code, payload.device_fingerprint)
    if err is not None:
        return err
    if not code:
        return _error("Token thiếu mã license.", 400)

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
    """POST body (token trong body, không lộ qua query string/log)."""
    if kind not in ALLOWED_KINDS:
        return _error(f"Loại đồng bộ không hợp lệ: {kind}", 400)
    code, err = _resolve_code(payload.token, payload.code, payload.device_fingerprint)
    if err is not None:
        return err
    return _get_blob(kind, code, db)


@router.get("/{kind}", response_model=SyncResponse)
@limiter.limit(settings.rate_limit_verify)
def get_blob(
    kind: str,
    request: Request,
    token: str | None = None,
    code: str | None = None,
    device_fingerprint: str = "",
    db: Session = Depends(get_db),
):
    """GET tiện cho debug; client thật nên dùng POST /{kind}/get để token nằm trong body."""
    if kind not in ALLOWED_KINDS:
        return _error(f"Loại đồng bộ không hợp lệ: {kind}", 400)
    if len(device_fingerprint) < 8:
        return _error("Thiếu device_fingerprint.", 400)
    resolved, err = _resolve_code(token, code, device_fingerprint)
    if err is not None:
        return err
    return _get_blob(kind, resolved, db)
