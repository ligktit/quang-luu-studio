"""Client-facing: kiểm tra & tải bản cập nhật."""
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AppVersion, VelopackRelease
from app.schemas import UpdateCheckResponse
from app.security import rollout_bucket
from app.services import storage, velopack_feed

router = APIRouter(prefix="/api/v1/updates", tags=["updates"])
# Route không prefix: link tải cố định cho lần cài đầu.
public_router = APIRouter(tags=["updates"])


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


# ── Velopack (bản 1.9.0 trở đi) ─────────────────────────────────────────────
# Mã máy nằm trong ĐƯỜNG DẪN vì Velopack nối tên file vào URL gốc của feed.
# Route releases.win.json phải khai báo TRƯỚC route {filename}.
@router.get("/velopack/{fingerprint}/releases.win.json")
def velopack_feed_json(fingerprint: str, db: Session = Depends(get_db)):
    if not velopack_feed.valid_fingerprint(fingerprint):
        return Response(status_code=404)
    rows = db.scalars(select(VelopackRelease)).all()
    return JSONResponse(velopack_feed.build_feed(rows, fingerprint))


@router.get("/velopack/{fingerprint}/{filename}")
def velopack_file(fingerprint: str, filename: str, db: Session = Depends(get_db)):
    if not velopack_feed.valid_fingerprint(fingerprint):
        return Response(status_code=404)
    rows = db.scalars(select(VelopackRelease).where(VelopackRelease.status == "xong")).all()
    if filename not in velopack_feed.served_filenames(rows):
        return Response(status_code=404)
    path = velopack_feed.file_path(filename)
    if path is None:
        return Response(status_code=404)
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@public_router.get("/tai-ve")
def tai_ve(db: Session = Depends(get_db)):
    """Bộ cài lần đầu: bản ổn định mới nhất đã phát cho 100% máy."""
    rows = db.scalars(
        select(VelopackRelease).where(
            VelopackRelease.status == "xong",
            VelopackRelease.is_active.is_(True),
            VelopackRelease.rollout_percent >= 100,
        )
    ).all()
    rows = [r for r in rows if r.setup_filename]
    if not rows:
        return Response(status_code=404, content="Chưa có bản cài", media_type="text/plain; charset=utf-8")
    best = max(rows, key=lambda r: velopack_feed.parse_semver(r.version))
    path = velopack_feed.file_path(best.setup_filename)
    if path is None:
        return Response(status_code=404, content="Thiếu file bản cài", media_type="text/plain; charset=utf-8")
    return FileResponse(path, media_type="application/octet-stream", filename="QuangLuuStudio-CaiDat.exe")
