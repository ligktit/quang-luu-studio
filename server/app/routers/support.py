"""Client-facing: kênh hỗ trợ HAI CHIỀU khách ↔ dev.

Khác `crashes.py` (một chiều, tự động, gộp theo hash traceback): ở đây khách chủ
động viết, dev trả lời trên admin web, khách đọc lại ngay trong app.

Xác thực: CỐ TÌNH chỉ dựa vào device_fingerprint, không đòi license token. Người
cần hỗ trợ nhất chính là người đang không kích hoạt được — bắt buộc token là tự
khoá cửa với họ. Chống lạm dụng bằng rate-limit (settings.rate_limit_support).

Quyền riêng tư: mọi truy cập ticket đều ràng theo device_fingerprint của chính
máy tạo ticket. KHÔNG cho tra theo license_code — mã license là chuỗi ngắn hay bị
chụp màn hình gửi cho nhau, mà ticket thì chứa số điện thoại/Zalo của khách.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import SupportMessage, SupportTicket
from app.schemas import (
    SupportInboxRequest,
    SupportInboxResponse,
    SupportReadRequest,
    SupportReplyRequest,
    SupportResponse,
    SupportTicketRequest,
)
from app.security import limiter

router = APIRouter(prefix="/api/v1/support", tags=["support"])

# Loại yêu cầu hợp lệ. Giá trị lạ → quy về "khac" thay vì báo lỗi: người dùng
# không nên bị chặn gửi hỗ trợ chỉ vì client cũ gửi nhãn khác.
CATEGORIES = {"loi", "huong_dan", "tinh_nang", "khac"}

# Số ticket trả về cho một máy. Đủ để khách theo dõi, không đủ để biến inbox
# thành một cú tải nặng.
INBOX_LIMIT = 20


def _error(message: str, http_status: int) -> JSONResponse:
    body = SupportResponse(ok=False, message=message).model_dump(mode="json")
    return JSONResponse(status_code=http_status, content=body)


def _make_ticket_code(ticket_id: int) -> str:
    return f"HT-{ticket_id:06d}"


def _find_own_ticket(db: Session, ticket_code: str, fingerprint: str) -> SupportTicket | None:
    """Ticket phải vừa đúng mã VỪA đúng máy đã tạo — biết mã thôi không đủ."""
    return db.scalar(
        select(SupportTicket).where(
            SupportTicket.ticket_code == ticket_code,
            SupportTicket.device_fp == fingerprint,
        )
    )


@router.post("/ticket", response_model=SupportResponse)
@limiter.limit(settings.rate_limit_support)
def create_ticket(request: Request, payload: SupportTicketRequest, db: Session = Depends(get_db)):
    category = payload.category if payload.category in CATEGORIES else "khac"
    ticket = SupportTicket(
        ticket_code="",  # điền sau khi có id
        license_code=payload.license_code,
        device_fp=payload.device_fingerprint,
        hostname=payload.hostname,
        os_info=payload.os,
        app_version=payload.app_version,
        contact=payload.contact,
        category=category,
        subject=payload.subject.strip(),
        status="new",
        log_excerpt=payload.log_excerpt,
        unread_client=False,
    )
    db.add(ticket)
    db.flush()  # lấy id để sinh mã người đọc được
    ticket.ticket_code = _make_ticket_code(ticket.id)
    db.add(SupportMessage(ticket_id=ticket.id, sender="customer", body=payload.body.strip()))
    db.commit()
    db.refresh(ticket)
    return SupportResponse(ok=True, ticket_code=ticket.ticket_code)


@router.post("/ticket/reply", response_model=SupportResponse)
@limiter.limit(settings.rate_limit_support)
def reply_ticket(request: Request, payload: SupportReplyRequest, db: Session = Depends(get_db)):
    ticket = _find_own_ticket(db, payload.ticket_code, payload.device_fingerprint)
    if ticket is None:
        return _error("Không tìm thấy yêu cầu hỗ trợ này.", 404)
    if ticket.status == "closed":
        return _error("Yêu cầu này đã đóng. Vui lòng gửi yêu cầu mới.", 409)

    db.add(SupportMessage(ticket_id=ticket.id, sender="customer", body=payload.body.strip()))
    # Khách vừa nói tiếp → không còn là "dev đã trả lời xong".
    ticket.status = "open"
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    return SupportResponse(ok=True, ticket_code=ticket.ticket_code)


@router.post("/inbox", response_model=SupportInboxResponse)
@limiter.limit(settings.rate_limit_verify)
def inbox(request: Request, payload: SupportInboxRequest, db: Session = Depends(get_db)):
    tickets = list(
        db.scalars(
            select(SupportTicket)
            .where(SupportTicket.device_fp == payload.device_fingerprint)
            .order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
            .limit(INBOX_LIMIT)
        ).all()
    )
    unread = sum(1 for t in tickets if t.unread_client)
    return SupportInboxResponse(ok=True, unread_count=unread, tickets=tickets)


@router.post("/ticket/read", response_model=SupportResponse)
@limiter.limit(settings.rate_limit_verify)
def mark_read(request: Request, payload: SupportReadRequest, db: Session = Depends(get_db)):
    ticket = _find_own_ticket(db, payload.ticket_code, payload.device_fingerprint)
    if ticket is None:
        return _error("Không tìm thấy yêu cầu hỗ trợ này.", 404)
    ticket.unread_client = False
    db.commit()
    return SupportResponse(ok=True, ticket_code=ticket.ticket_code)
