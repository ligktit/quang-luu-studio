"""Admin web UI — đăng nhập mật khẩu, quản lý user / license / version / crash."""
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
from app.models import AdminUser, AppVersion, CrashReport, Device, License, User
from app.security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    make_session,
    verify_password,
)
from app.services import codegen, storage

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
        "versions": db.scalar(select(func.count(AppVersion.id))),
    }
    return templates.TemplateResponse(request, "dashboard.html", {"admin": admin, "stats": stats})


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


# ── Licenses ──
@router.get("/licenses", response_class=HTMLResponse)
def licenses_page(request: Request, admin: str = Depends(current_admin), db: Session = Depends(get_db)):
    licenses = db.scalars(select(License).order_by(License.issued_at.desc())).all()
    users = db.scalars(select(User).order_by(User.name)).all()
    return templates.TemplateResponse(
        request, "licenses.html", {"admin": admin, "licenses": licenses, "users": users}
    )


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
    lic = db.get(License, lic_id)
    if lic:
        for d in lic.devices:
            d.revoked = True
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
