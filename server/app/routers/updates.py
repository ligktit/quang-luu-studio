"""Client-facing: kiểm tra & tải bản cập nhật."""
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AppVersion
from app.schemas import UpdateCheckResponse
from app.security import rollout_bucket
from app.services import storage

router = APIRouter(prefix="/api/v1/updates", tags=["updates"])


def _parse_semver(v: str) -> tuple[int, int, int]:
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else (0, 0, 0)


def _is_newer(remote: str, local: str) -> bool:
    return _parse_semver(remote) > _parse_semver(local)


@router.get("/check", response_model=UpdateCheckResponse)
def check(
    request: Request,
    version: str = "0.0.0",
    channel: str = "stable",
    fingerprint: str = "",
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(AppVersion)
        .where(AppVersion.channel == channel, AppVersion.is_active.is_(True))
        .order_by(AppVersion.published_at.desc())
    ).all()

    bucket = rollout_bucket(fingerprint) if fingerprint else 0
    for av in rows:
        if not _is_newer(av.version, version):
            continue
        if av.rollout_percent < 100 and bucket >= av.rollout_percent:
            continue  # chưa tới lượt máy này trong đợt rollout
        url = f"{settings.base_url.rstrip('/')}/api/v1/updates/download/{av.version}"
        return UpdateCheckResponse(
            update_available=True,
            version=av.version,
            download_url=url,
            sha256=av.sha256,
            size_bytes=av.size_bytes,
            release_notes=av.release_notes or "",
            mandatory=av.mandatory,
            published_at=av.published_at.isoformat() if av.published_at else "",
        )

    return UpdateCheckResponse(update_available=False)


@router.get("/download/{version}")
def download(version: str, request: Request, channel: str = "stable", db: Session = Depends(get_db)):
    av = db.scalar(
        select(AppVersion).where(AppVersion.version == version, AppVersion.channel == channel)
    )
    if av is None:
        return Response(status_code=404, content="Version not found")
    path = storage.resolve(av.filename)
    if path is None:
        return Response(status_code=404, content="File missing on server")
    # FileResponse hỗ trợ HTTP Range sẵn → client _downloader.py resume được.
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=f"QuangLuuStudio_Setup_{version}.exe",
    )
