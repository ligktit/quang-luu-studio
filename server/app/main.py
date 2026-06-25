"""FastAPI app — ráp routers, rate-limit, redirect admin, healthcheck."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.deps import AdminRequired
from app.routers import activation, admin, crashes, sync, updates
from app.security import limiter

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

app = FastAPI(title=settings.app_name, docs_url="/api/docs" if settings.debug else None)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(AdminRequired)
async def _admin_required_handler(request: Request, exc: AdminRequired):
    return RedirectResponse("/admin/login", status_code=303)


app.include_router(activation.router)
app.include_router(sync.router)
app.include_router(updates.router)
app.include_router(crashes.router)
app.include_router(admin.router)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": settings.app_name}


@app.get("/")
def root():
    return RedirectResponse("/admin")
