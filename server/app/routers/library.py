"""Thư viện tone cộng đồng: máy nào đã dò thì cả mạng lưới dùng lại.

Khác `sync.py` một trời một vực dù nghe giống nhau:
  - sync.py  : blob RIÊNG TƯ của một license, đồng bộ giữa các máy của CHÍNH
               khách đó. Premium.
  - file này : dữ liệu DÙNG CHUNG giữa các khách hàng. Mọi máy đã kích hoạt đều
               đọc và ghi được — càng nhiều máy đóng góp thì tone càng chính xác.

Luật "kết quả nào đúng" nằm ở app/services/tonelib.py.
"""
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import SharedTone, SharedToneVote
from app.schemas import (
    LibraryContributeRequest,
    LibraryContributeResponse,
    LibraryLookupRequest,
    LibraryLookupResponse,
    LibraryReportRequest,
    LibraryReportResponse,
    ToneResult,
)
from app.security import limiter
from app.services import licensing, tonelib

router = APIRouter(prefix="/api/v1/library", tags=["library"])


def _error(model, message: str, http_status: int) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content=model(ok=False, message=message).model_dump(mode="json"),
    )


def _authorize(payload, db: Session):
    """Mọi máy ĐÃ KÍCH HOẠT đều được đọc/ghi — không giới hạn ở Premium.

    Cố ý: thư viện này sống bằng hiệu ứng mạng. Chặn Standard đóng góp là tự
    bóp nguồn dữ liệu của chính mình.
    """
    return licensing.authorize_device(
        db, payload.token, payload.device_fingerprint, require_premium=False
    )


def _to_result(tone: SharedTone) -> ToneResult:
    try:
        timeline = json.loads(tone.timeline or "[]")
    except (ValueError, TypeError):
        timeline = []
    return ToneResult(
        song_key=tone.song_key,
        title=tone.title or "",
        primary_key=tone.primary_key or "",
        source=tone.source or "auto",
        votes=int(tone.votes or 0),
        payload_hash=tone.payload_hash,
        timeline=timeline,
    )


@router.post("/lookup", response_model=LibraryLookupResponse)
@limiter.limit(settings.rate_limit_library)
def lookup(request: Request, payload: LibraryLookupRequest, db: Session = Depends(get_db)):
    _code, message, status = _authorize(payload, db)
    if message is not None:
        return _error(LibraryLookupResponse, message, status)

    keys = [k for k in dict.fromkeys(payload.keys) if tonelib.valid_song_key(k)]
    if not keys:
        return LibraryLookupResponse(ok=True, results={})

    rows = db.scalars(select(SharedTone).where(SharedTone.song_key.in_(keys))).all()

    by_song: dict[str, list] = {}
    for tone in rows:
        by_song.setdefault(tone.song_key, []).append(tone)

    results = {}
    for song_key, variants in by_song.items():
        best = tonelib.best_variant(variants)
        if best is not None:
            results[song_key] = _to_result(best)
    return LibraryLookupResponse(ok=True, results=results)


def _record_vote(db: Session, tone: SharedTone, fingerprint: str, kind: str) -> bool:
    """Ghi phiếu nếu máy này chưa bỏ. Trả True nếu là phiếu mới."""
    existing = db.scalar(
        select(SharedToneVote).where(
            SharedToneVote.tone_id == tone.id,
            SharedToneVote.device_fp == fingerprint,
            SharedToneVote.kind == kind,
        )
    )
    if existing is not None:
        return False
    db.add(SharedToneVote(tone_id=tone.id, device_fp=fingerprint, kind=kind))
    if kind == "report":
        tone.reports = int(tone.reports or 0) + 1
    else:
        tone.votes = int(tone.votes or 0) + 1
    return True


def _withdraw_other_votes(db: Session, song_key: str, keep_tone_id: int, fingerprint: str) -> None:
    """Một máy chỉ giữ MỘT phiếu thuận cho mỗi bài.

    Khi người dùng sửa tay rồi đóng góp bản mới, phiếu cũ của chính máy đó phải
    được rút lại — nếu không, một máy đổi ý ba lần là bơm ba phiếu cho ba biến
    thể mâu thuẫn nhau của cùng một bài.
    """
    siblings = db.scalars(
        select(SharedTone).where(SharedTone.song_key == song_key, SharedTone.id != keep_tone_id)
    ).all()
    if not siblings:
        return
    votes = db.scalars(
        select(SharedToneVote).where(
            SharedToneVote.tone_id.in_([t.id for t in siblings]),
            SharedToneVote.device_fp == fingerprint,
            SharedToneVote.kind == "vote",
        )
    ).all()
    by_id = {t.id: t for t in siblings}
    for vote in votes:
        tone = by_id.get(vote.tone_id)
        if tone is not None:
            tone.votes = max(0, int(tone.votes or 0) - 1)
        db.delete(vote)


@router.post("/contribute", response_model=LibraryContributeResponse)
@limiter.limit(settings.rate_limit_library)
def contribute(request: Request, payload: LibraryContributeRequest, db: Session = Depends(get_db)):
    _code, message, status = _authorize(payload, db)
    if message is not None:
        return _error(LibraryContributeResponse, message, status)

    fingerprint = payload.device_fingerprint
    accepted = 0
    rejected = 0

    for item in payload.items:
        if not tonelib.valid_song_key(item.song_key):
            rejected += 1
            continue
        raw = [entry.model_dump() for entry in item.timeline]
        normalized = tonelib.normalize_timeline(raw)
        if not normalized:
            rejected += 1
            continue

        source = item.source.lower() if item.source.lower() in tonelib.SOURCES else "auto"
        digest = tonelib.payload_hash(item.song_key, normalized)

        tone = db.scalar(
            select(SharedTone).where(
                SharedTone.song_key == item.song_key,
                SharedTone.payload_hash == digest,
            )
        )
        if tone is None:
            tone = SharedTone(
                song_key=item.song_key,
                payload_hash=digest,
                title=(item.title or "").strip()[:300],
                primary_key=(item.primary_key or "").strip()[:20],
                timeline=json.dumps(raw[: tonelib.MAX_ENTRIES], ensure_ascii=False),
                source=source,
                votes=0,
                reports=0,
            )
            db.add(tone)
            db.flush()
        else:
            # Cùng chuỗi tone nhưng có người sửa tay xác nhận → nâng nguồn lên
            # "human", không bao giờ hạ ngược lại.
            if source == "human" and tone.source != "human":
                tone.source = "human"
            if item.title and not tone.title:
                tone.title = item.title.strip()[:300]

        _record_vote(db, tone, fingerprint, "vote")
        _withdraw_other_votes(db, item.song_key, tone.id, fingerprint)
        accepted += 1

    db.commit()
    return LibraryContributeResponse(ok=True, accepted=accepted, rejected=rejected)


@router.post("/report", response_model=LibraryReportResponse)
@limiter.limit(settings.rate_limit_library)
def report(request: Request, payload: LibraryReportRequest, db: Session = Depends(get_db)):
    """Báo một biến thể sai. Không có payload_hash thì báo biến thể đang thắng."""
    _code, message, status = _authorize(payload, db)
    if message is not None:
        return _error(LibraryReportResponse, message, status)

    if not tonelib.valid_song_key(payload.song_key):
        return _error(LibraryReportResponse, "Mã bài không hợp lệ.", 400)

    variants = db.scalars(
        select(SharedTone).where(SharedTone.song_key == payload.song_key)
    ).all()
    if not variants:
        return LibraryReportResponse(ok=True, message="Bài này chưa có trong thư viện chung.")

    if payload.payload_hash:
        target = next((t for t in variants if t.payload_hash == payload.payload_hash), None)
    else:
        target = tonelib.best_variant(variants)
    if target is None:
        return LibraryReportResponse(ok=True, message="Không tìm thấy bản tone cần báo.")

    _record_vote(db, target, payload.device_fingerprint, "report")
    db.commit()
    return LibraryReportResponse(ok=True)
