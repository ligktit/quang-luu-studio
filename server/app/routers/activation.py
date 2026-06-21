"""Client-facing: kích hoạt & xác thực license."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas import ActivateRequest, LicenseResponse, VerifyRequest
from app.security import decode_license_token, limiter
from app.services import licensing
from app.services.licensing import LicenseError

router = APIRouter(prefix="/api/v1", tags=["activation"])


def _error(e: LicenseError) -> JSONResponse:
    body = LicenseResponse(valid=False, status=e.status, message=e.message).model_dump(mode="json")
    return JSONResponse(status_code=e.http_status, content=body)


@router.post("/activate", response_model=LicenseResponse)
@limiter.limit(settings.rate_limit_activate)
def activate(request: Request, payload: ActivateRequest, db: Session = Depends(get_db)):
    try:
        result = licensing.activate(
            db,
            code=payload.code,
            fingerprint=payload.device_fingerprint,
            hostname=payload.hostname,
            os=payload.os,
            app_version=payload.app_version,
        )
        return LicenseResponse(**result)
    except LicenseError as e:
        return _error(e)


@router.post("/license/verify", response_model=LicenseResponse)
@limiter.limit(settings.rate_limit_verify)
def verify(request: Request, payload: VerifyRequest, db: Session = Depends(get_db)):
    # Lấy code: ưu tiên token (đã ký) → fallback code thô.
    code = payload.code
    if payload.token:
        decoded = decode_license_token(payload.token)
        if decoded is None:
            return _error(LicenseError("Token không hợp lệ hoặc hết hạn.", status="invalid", http_status=401))
        if decoded.get("fp") != payload.device_fingerprint:
            return _error(LicenseError("Token không khớp thiết bị.", status="invalid", http_status=403))
        code = decoded.get("code")

    if not code:
        return _error(LicenseError("Thiếu mã hoặc token.", status="invalid", http_status=400))

    try:
        result = licensing.verify(
            db, code=code, fingerprint=payload.device_fingerprint, app_version=payload.app_version
        )
        return LicenseResponse(**result)
    except LicenseError as e:
        return _error(e)
