"""FastAPI app — ráp routers, rate-limit, redirect admin, healthcheck."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.deps import AdminRequired
from app.routers import activation, admin, crashes, library, support, sync, updates
from app.security import check_signing_key_ready, limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger(__name__)

# Chết sớm nếu thiếu khoá ký: server license không có khoá thì mọi lần kích hoạt
# sẽ lỗi 500 giữa chừng — thà không khởi động được với thông báo rõ ràng.
check_signing_key_ready()

app = FastAPI(title=settings.app_name, docs_url="/api/docs" if settings.debug else None)

# Rate limiting
app.state.limiter = limiter


# ── Lỗi TẠM THỜI phải nói rõ là tạm thời ─────────────────────────────────────
# Client coi mọi response không có field `status` là "giấy phép không hợp lệ" và
# XOÁ license cache. Nghĩa là một cú 429 hay 502 lúc restart server đủ để đá
# hàng loạt máy đang chạy ra màn hình kích hoạt.
#
# Vì các máy ngoài thị trường không cập nhật ngay được, server phải tự bảo đảm:
# mọi lỗi tạm thời đều trả JSON có `status` NẰM NGOÀI tập trạng thái "mất quyền"
# ({revoked, expired, not_activated, invalid}) để client cũ giữ nguyên cache.
# Xem docs/LICENSING_KICKOUT_FIX_PLAN.md.
def _soft_error(status: str, message: str, http_status: int) -> JSONResponse:
    return JSONResponse(
        status_code=http_status,
        content={"valid": False, "status": status, "message": message},
        headers={"Retry-After": "60"},
    )


@app.exception_handler(RateLimitExceeded)
async def _rate_limited(request: Request, exc: RateLimitExceeded):
    log.warning("Rate limit: %s %s (%s)", request.method, request.url.path, exc.detail)
    return _soft_error("rate_limited", "Máy chủ đang bận, vui lòng thử lại sau.", 429)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    log.exception("Lỗi chưa xử lý tại %s %s", request.method, request.url.path)
    return _soft_error("server_error", "Máy chủ gặp sự cố tạm thời.", 500)


@app.exception_handler(AdminRequired)
async def _admin_required_handler(request: Request, exc: AdminRequired):
    return RedirectResponse("/admin/login", status_code=303)


app.include_router(activation.router)
app.include_router(sync.router)
app.include_router(updates.router)
app.include_router(crashes.router)
app.include_router(support.router)
app.include_router(library.router)
app.include_router(admin.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": settings.app_name}


@app.get("/")
def root():
    return RedirectResponse("/admin")
