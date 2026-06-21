"""Client-facing: nhận crash report tự động."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import CrashReport
from app.schemas import CrashRequest, CrashResponse
from app.security import limiter, sha256_text

router = APIRouter(prefix="/api/v1", tags=["crash"])


@router.post("/crash", response_model=CrashResponse)
@limiter.limit(settings.rate_limit_crash)
def report_crash(request: Request, payload: CrashRequest, db: Session = Depends(get_db)):
    # Dedupe theo hash(version + traceback) → cùng lỗi chỉ tăng count.
    fp_hash = sha256_text(f"{payload.app_version}|{payload.traceback}")

    existing = db.scalar(select(CrashReport).where(CrashReport.fingerprint_hash == fp_hash))
    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.count += 1
        existing.last_seen = now
        existing.device_fp = payload.device_fingerprint or existing.device_fp
        existing.license_code = payload.license_code or existing.license_code
        if existing.status == "resolved":
            existing.status = "new"  # tái xuất hiện
        db.commit()
        return CrashResponse(ok=True, report_id=existing.id)

    report = CrashReport(
        fingerprint_hash=fp_hash,
        device_fp=payload.device_fingerprint,
        license_code=payload.license_code,
        app_version=payload.app_version,
        os_info=payload.os,
        traceback=payload.traceback,
        log_excerpt=payload.log_excerpt,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return CrashResponse(ok=True, report_id=report.id)
