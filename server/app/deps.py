"""Shared FastAPI dependencies."""
from fastapi import Request
from fastapi.responses import RedirectResponse

from app.security import SESSION_COOKIE, read_session


class AdminRequired(Exception):
    """Raise khi route admin chưa đăng nhập → redirect tới /admin/login."""


def current_admin(request: Request) -> str:
    """Trả username admin hoặc raise AdminRequired."""
    username = read_session(request.cookies.get(SESSION_COOKIE))
    if not username:
        raise AdminRequired()
    return username
