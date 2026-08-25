"""Admin web UI — đăng nhập mật khẩu, quản lý user / license / version / crash."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import current_admin
from app.models import (
    AdminUser,
    AppVersion,
    CrashReport,
    Device,
    License,
    SharedTone,
    SupportMessage,
    SupportTicket,
    User,
)
from app.security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    make_session,
    verify_password,
)
from app.services import codegen, storage, tonelib

router = APIRouter(prefix="/admin", tags=["admin"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def _check_admin_credentials(db: Session, username: str, password: str) -> bool:
    # 1) AdminUser trong DB
    admin = db.scalar(select(AdminUser).where(AdminUser.username == username))
    if admin and verify_password(password, admin.password_hash):
        return True
    # 2) Fallback từ .env (tiện lần đầu, trước khi tạo AdminUser)
    if username == settings.admin_username:
        if settings.admin_password_hash and verify_password(password, settings.admin_password_hash):
            return True
        if settings.admin_password and password == settings.admin_password:
            return True
    return False


# ── Auth ──
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if not _check_admin_credentials(db, username, password):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Sai tài khoản hoặc mật khẩu."}, status_code=401
        )
    resp = _redirect("/admin")
    resp.set_cookie(
        SESSION_COOKIE,
        make_session(username),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
    )
    return resp


@router.get("/logout")
def logout():
    resp = _redirect("/admin/login")
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ── Dashboard ──
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    stats = {
        "users": db.scalar(select(func.count(User.id))),
        "licenses": db.scalar(select(func.count(License.id))),
        "active": db.scalar(select(func.count(License.id)).where(License.status == "active")),
        "devices": db.scalar(select(func.count(Device.id))),
        "crashes_new": db.scalar(select(func.count(CrashReport.id)).where(CrashReport.status == "new")),
        "support_new": db.scalar(select(func.count(SupportTicket.id)).where(SupportTicket.status == "new")),
        "versions": db.scalar(select(func.count(AppVersion.id))),
    }

    # Sức khoẻ giấy phép — dấu hiệu sớm của sự cố "máy dùng vài ngày bị đá ra".
    devices = list(db.scalars(select(Device)).all())
    licenses = list(db.scalars(select(License)).all())
    version_counts: dict[str, int] = {}
    for d in devices:
        version_counts[d.app_version or "?"] = version_counts.get(d.app_version or "?", 0) + 1
    top_version, top_n = max(version_counts.items(), key=lambda kv: kv[1], default=("—", 0))
    health = {
        "stale": sum(1 for d in devices if not d.revoked and _is_stale(d)),
        "stale30": sum(1 for d in devices if not d.revoked and _is_stale(d, 30)),
        "blocked": sum(1 for d in devices if d.revoked),
        "drift": sum(1 for l in licenses if _has_drift(l)),
        "full": sum(1 for l in licenses if len(l.active_devices) >= l.max_devices),
        "top_version": f"v{top_version} ({top_n})" if top_n else "—",
    }
    return templates.TemplateResponse(
        request, "dashboard.html", {"admin": admin, "stats": stats, "health": health}
    )


# ── Users ──
@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return templates.TemplateResponse(request, "users.html", {"admin": admin, "users": users})


@router.post("/users")
def create_user(
    name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    note: str = Form(""),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    db.add(User(name=name.strip(), email=email.strip() or None, phone=phone.strip() or None, note=note.strip() or None))
    db.commit()
    return _redirect("/admin/users")


@router.post("/users/{user_id}/delete")
def delete_user(user_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if u:
        db.delete(u)
        db.commit()
    return _redirect("/admin/users")


# ── Bộ lọc theo dõi ──
# Các nhãn dưới đây là kết quả chẩn đoán sự cố "máy dùng vài ngày bị đá ra"
# (docs/LICENSING_KICKOUT_FIX_PLAN.md). Gom vào UI để không phải mở SQL mỗi lần
# khách gọi.
STALE_DAYS = 7


def _aware(dt: datetime | None) -> datetime | None:
    """Postgres trả aware, SQLite (test) trả naive — quy về UTC để so sánh được."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _days_quiet(device: Device) -> float | None:
    """Số ngày kể từ lần check-in gần nhất. None = chưa bao giờ check-in."""
    ts = _aware(device.last_check_in)
    if ts is None:
        return None
    return (datetime.now(timezone.utc) - ts).total_seconds() / 86400


def _is_stale(device: Device, days: int = STALE_DAYS) -> bool:
    quiet = _days_quiet(device)
    return quiet is None or quiet > days


def _has_drift(lic: License) -> bool:
    """Cùng một hostname xuất hiện ở nhiều bản ghi → fingerprint đã đổi."""
    seen: set[str] = set()
    for d in lic.devices:
        name = (d.hostname or "").strip().lower()
        if not name:
            continue
        if name in seen:
            return True
        seen.add(name)
    return False


LICENSE_FLAGS = {
    # slug: (nhãn hiển thị, hàm lọc)
    "blocked": ("Có máy bị chặn", lambda l: any(d.revoked for d in l.devices)),
    "full":    ("Đã đủ slot máy", lambda l: len(l.active_devices) >= l.max_devices),
    "drift":   ("Nghi fingerprint đổi", _has_drift),
    "stale":   (f"Máy im >{STALE_DAYS} ngày",
                lambda l: bool(l.active_devices) and all(_is_stale(d) for d in l.active_devices)),
    "unbound": ("Chưa có máy nào", lambda l: not l.devices),
}


# ── Licenses ──
@router.get("/licenses", response_class=HTMLResponse)
def licenses_page(
    request: Request,
    q: str = "",
    status: str = "",
    plan: str = "",
    flag: str = "",
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    stmt = select(License)
    if status:
        stmt = stmt.where(License.status == status)
    if plan:
        stmt = stmt.where(License.plan == plan)
    licenses = list(db.scalars(stmt.order_by(License.issued_at.desc())).all())

    # Đếm trên TOÀN BỘ tập đã lọc theo status/plan, trước khi lọc tiếp bằng cờ —
    # để các nút cờ luôn hiện đúng số lượng thay vì tự trừ về 0 sau khi bấm.
    counts = {slug: sum(1 for l in licenses if fn(l)) for slug, (_, fn) in LICENSE_FLAGS.items()}

    needle = q.strip().lower()
    if needle:
        licenses = [
            l for l in licenses
            if needle in l.code.lower()
            or (l.user and needle in (l.user.name or "").lower())
            or any(needle in (d.hostname or "").lower() for d in l.devices)
        ]
    if flag in LICENSE_FLAGS:
        licenses = [l for l in licenses if LICENSE_FLAGS[flag][1](l)]

    users = db.scalars(select(User).order_by(User.name)).all()
    return templates.TemplateResponse(request, "licenses.html", {
        "admin": admin,
        "licenses": licenses,
        "users": users,
        "q": q,
        "status": status,
        "plan": plan,
        "flag": flag,
        "flags": {slug: label for slug, (label, _) in LICENSE_FLAGS.items()},
        "counts": counts,
        "total": db.scalar(select(func.count(License.id))),
        "days_quiet": _days_quiet,
        "stale_days": STALE_DAYS,
    })


# ── Devices ──
@router.get("/devices", response_class=HTMLResponse)
def devices_page(
    request: Request,
    q: str = "",
    version: str = "",
    state: str = "",
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    """
    Danh sách thiết bị — nơi theo dõi phủ sóng bản cập nhật và các máy đang im.

    Cột `app_version` là cách duy nhất biết bản vá đã tới được bao nhiêu máy;
    cột `check-in cuối` cho biết máy nào sắp hết grace.
    """
    devices = list(db.scalars(
        select(Device).order_by(Device.last_check_in.desc().nullslast())
    ).all())

    versions: dict[str, int] = {}
    for d in devices:
        versions[d.app_version or "?"] = versions.get(d.app_version or "?", 0) + 1
    versions = dict(sorted(versions.items(), key=lambda kv: kv[0], reverse=True))

    summary = {
        "total": len(devices),
        "blocked": sum(1 for d in devices if d.revoked),
        "stale": sum(1 for d in devices if not d.revoked and _is_stale(d)),
        "stale30": sum(1 for d in devices if not d.revoked and _is_stale(d, 30)),
    }

    if version:
        devices = [d for d in devices if (d.app_version or "?") == version]
    if state == "blocked":
        devices = [d for d in devices if d.revoked]
    elif state == "active":
        devices = [d for d in devices if not d.revoked]
    elif state == "stale":
        devices = [d for d in devices if not d.revoked and _is_stale(d)]
    needle = q.strip().lower()
    if needle:
        devices = [
            d for d in devices
            if needle in (d.hostname or "").lower()
            or needle in d.fingerprint.lower()
            or needle in (d.license.code if d.license else "").lower()
        ]

    return templates.TemplateResponse(request, "devices.html", {
        "admin": admin,
        "devices": devices,
        "summary": summary,
        "versions": versions,
        "q": q,
        "version": version,
        "state": state,
        "days_quiet": _days_quiet,
        "stale_days": STALE_DAYS,
    })


@router.post("/licenses/generate")
def generate_licenses(
    count: int = Form(1),
    max_devices: int = Form(1),
    plan: str = Form("standard"),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    count = max(1, min(count, 500))
    for code in codegen.generate_codes(count):
        db.add(License(code=code, plan=plan, max_devices=max_devices, status="unused"))
    db.commit()
    return _redirect("/admin/licenses")


@router.post("/licenses/{lic_id}/assign")
def assign_license(
    lic_id: int,
    user_id: int = Form(...),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    lic = db.get(License, lic_id)
    if lic:
        lic.user_id = user_id or None
        db.commit()
    return _redirect("/admin/licenses")


@router.post("/licenses/{lic_id}/set-plan")
def set_license_plan(
    lic_id: int,
    plan: str = Form("standard"),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    plan = plan.strip().lower()
    if plan not in ("standard", "premium"):
        plan = "standard"
    lic = db.get(License, lic_id)
    if lic:
        lic.plan = plan
        db.commit()
    return _redirect("/admin/licenses")


@router.post("/licenses/{lic_id}/revoke")
def revoke_license(lic_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    lic = db.get(License, lic_id)
    if lic:
        lic.status = "revoked"
        db.commit()
    return _redirect("/admin/licenses")


@router.post("/licenses/{lic_id}/extend")
def extend_license(
    lic_id: int,
    days: int = Form(365),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    lic = db.get(License, lic_id)
    if lic:
        base = lic.expires_at or datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        base = max(base, datetime.now(timezone.utc))
        lic.expires_at = base + timedelta(days=days)
        if lic.status == "expired":
            lic.status = "active"
        db.commit()
    return _redirect("/admin/licenses")


@router.post("/licenses/{lic_id}/reset-devices")
def reset_devices(lic_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    """
    Gỡ toàn bộ ràng buộc máy của một mã, để khách kích hoạt lại từ đầu.

    XOÁ hẳn bản ghi chứ không đặt revoked=True: activate() tìm device theo
    fingerprint TRƯỚC khi đếm slot, nên một bản ghi revoked còn nằm đó sẽ chặn
    vĩnh viễn đúng cái máy vừa được "reset" (`Thiết bị này đã bị thu hồi quyền`).
    revoked giữ nguyên ý nghĩa "cấm riêng một máy" — dùng nút xoá từng máy hoặc
    thu hồi cả mã cho việc đó.
    """
    lic = db.get(License, lic_id)
    if lic:
        for d in list(lic.devices):
            db.delete(d)
        db.commit()
    return _redirect("/admin/licenses")


@router.post("/devices/{device_id}/delete")
def delete_device(device_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    """Gỡ MỘT máy khỏi mã — dùng khi fingerprint của khách đổi và chiếm mất slot."""
    d = db.get(Device, device_id)
    if d:
        db.delete(d)
        db.commit()
    return _redirect("/admin/licenses")


# ── Versions ──
@router.get("/versions", response_class=HTMLResponse)
def versions_page(request: Request, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    versions = db.scalars(select(AppVersion).order_by(AppVersion.published_at.desc())).all()
    return templates.TemplateResponse(request, "versions.html", {"admin": admin, "versions": versions})


@router.post("/versions/upload")
async def upload_version(
    version: str = Form(...),
    channel: str = Form("stable"),
    release_notes: str = Form(""),
    mandatory: bool = Form(False),
    rollout_percent: int = Form(100),
    file: UploadFile = File(...),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    stored, sha256, size = storage.save_upload(version.strip(), file.filename, file.file)
    existing = db.scalar(
        select(AppVersion).where(AppVersion.version == version.strip(), AppVersion.channel == channel)
    )
    if existing:
        existing.filename = stored
        existing.sha256 = sha256
        existing.size_bytes = size
        existing.release_notes = release_notes
        existing.mandatory = mandatory
        existing.rollout_percent = max(0, min(rollout_percent, 100))
        existing.is_active = True
    else:
        db.add(AppVersion(
            version=version.strip(),
            channel=channel,
            filename=stored,
            sha256=sha256,
            size_bytes=size,
            release_notes=release_notes,
            mandatory=mandatory,
            rollout_percent=max(0, min(rollout_percent, 100)),
            is_active=True,
        ))
    db.commit()
    return _redirect("/admin/versions")


@router.post("/versions/{ver_id}/toggle")
def toggle_version(ver_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    av = db.get(AppVersion, ver_id)
    if av:
        av.is_active = not av.is_active
        db.commit()
    return _redirect("/admin/versions")


# ── Crashes ──
@router.get("/crashes", response_class=HTMLResponse)
def crashes_page(request: Request, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    crashes = db.scalars(select(CrashReport).order_by(CrashReport.last_seen.desc()).limit(200)).all()
    return templates.TemplateResponse(request, "crashes.html", {"admin": admin, "crashes": crashes})


@router.get("/crashes/{crash_id}", response_class=HTMLResponse)
def crash_detail(crash_id: int, request: Request, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    crash = db.get(CrashReport, crash_id)
    if crash and crash.status == "new":
        crash.status = "seen"
        db.commit()
    return templates.TemplateResponse(request, "crash_detail.html", {"admin": admin, "crash": crash})


@router.post("/crashes/{crash_id}/resolve")
def resolve_crash(crash_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    crash = db.get(CrashReport, crash_id)
    if crash:
        crash.status = "resolved"
        db.commit()
    return _redirect("/admin/crashes")


# ── Hỗ trợ ──
_SUPPORT_STATUSES = ("new", "open", "answered", "closed")


@router.get("/support", response_class=HTMLResponse)
def support_page(
    request: Request,
    status: str = "",
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    query = select(SupportTicket).order_by(SupportTicket.updated_at.desc(), SupportTicket.id.desc())
    if status in _SUPPORT_STATUSES:
        query = query.where(SupportTicket.status == status)
    tickets = db.scalars(query.limit(200)).all()
    return templates.TemplateResponse(
        request,
        "support.html",
        {"admin": admin, "tickets": tickets, "status": status, "statuses": _SUPPORT_STATUSES},
    )


@router.get("/support/{ticket_id}", response_class=HTMLResponse)
def support_detail(
    ticket_id: int,
    request: Request,
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    ticket = db.get(SupportTicket, ticket_id)
    # "new" nghĩa là dev CHƯA từng mở. Mở ra rồi thì chuyển sang "open" để bảng
    # tổng quan đếm đúng số việc còn chưa ai ngó tới.
    if ticket and ticket.status == "new":
        ticket.status = "open"
        db.commit()
    return templates.TemplateResponse(request, "support_detail.html", {"admin": admin, "ticket": ticket})


@router.post("/support/{ticket_id}/reply")
def support_reply(
    ticket_id: int,
    body: str = Form(...),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    ticket = db.get(SupportTicket, ticket_id)
    if ticket and body.strip():
        db.add(SupportMessage(ticket_id=ticket.id, sender="dev", body=body.strip()))
        ticket.status = "answered"
        # Cờ này là thứ bật chấm đỏ trong app khách — quên set là khách không
        # bao giờ biết đã có trả lời.
        ticket.unread_client = True
        ticket.updated_at = datetime.now(timezone.utc)
        db.commit()
    return _redirect(f"/admin/support/{ticket_id}")


@router.post("/support/{ticket_id}/status")
def support_set_status(
    ticket_id: int,
    status: str = Form(...),
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    ticket = db.get(SupportTicket, ticket_id)
    if ticket and status in _SUPPORT_STATUSES:
        ticket.status = status
        ticket.updated_at = datetime.now(timezone.utc)
        db.commit()
    return _redirect(f"/admin/support/{ticket_id}")


# ── Thư viện tone cộng đồng ──
def _count_segments(timeline_json: str) -> int:
    """Số mốc chuyển tone trong một biến thể (timeline lưu dạng JSON string)."""
    try:
        data = json.loads(timeline_json or "[]")
        return len(data) if isinstance(data, list) else 0
    except (ValueError, TypeError):
        return 0


@router.get("/library", response_class=HTMLResponse)
def library_page(
    request: Request,
    q: str = "",
    admin: str = Depends(current_admin),
    db: Session = Depends(get_db),
):
    """Van an toàn của thư viện chung: nhìn thấy và sửa được dữ liệu rác từ xa."""
    query = select(SharedTone)
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        query = query.where(SharedTone.song_key.ilike(like) | SharedTone.title.ilike(like))
    tones = db.scalars(query.order_by(SharedTone.last_seen.desc()).limit(400)).all()

    # Gom theo bài để dev thấy ngay các biến thể đang tranh nhau của cùng một bài.
    songs: dict[str, dict] = {}
    for tone in tones:
        songs.setdefault(tone.song_key, {"song_key": tone.song_key, "title": "", "variants": []})
        songs[tone.song_key]["variants"].append(tone)
        if tone.title and not songs[tone.song_key]["title"]:
            songs[tone.song_key]["title"] = tone.title

    groups = []
    for song in songs.values():
        best = tonelib.best_variant(song["variants"])
        song["variants"].sort(key=lambda t: tonelib.score(t), reverse=True)
        song["best_id"] = best.id if best is not None else None
        song["scores"] = {t.id: tonelib.score(t) for t in song["variants"]}
        song["segments"] = {t.id: _count_segments(t.timeline) for t in song["variants"]}
        groups.append(song)

    return templates.TemplateResponse(
        request, "library.html", {"admin": admin, "groups": groups, "q": term}
    )


@router.post("/library/{tone_id}/pin")
def library_pin(tone_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    tone = db.get(SharedTone, tone_id)
    if tone:
        if not tone.pinned:
            # Mỗi bài chỉ một bản ghim — ghim hai bản là mâu thuẫn tự thân.
            for sibling in db.scalars(
                select(SharedTone).where(SharedTone.song_key == tone.song_key)
            ).all():
                sibling.pinned = False
            tone.pinned = True
        else:
            tone.pinned = False
        db.commit()
    return _redirect("/admin/library")


@router.post("/library/{tone_id}/hide")
def library_hide(tone_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    tone = db.get(SharedTone, tone_id)
    if tone:
        tone.status = "ok" if tone.status == "hidden" else "hidden"
        db.commit()
    return _redirect("/admin/library")


@router.post("/library/{tone_id}/delete")
def library_delete(tone_id: int, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    tone = db.get(SharedTone, tone_id)
    if tone:
        db.delete(tone)
        db.commit()
    return _redirect("/admin/library")
