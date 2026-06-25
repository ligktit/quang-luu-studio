"""
Bảo mật: license token (JWT), hash mật khẩu admin, session cookie admin, rate-limit.
"""
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

# ── Rate limiter (gắn vào app.state.limiter trong main.py) ──
limiter = Limiter(key_func=get_remote_address)

# ── Password hashing (admin) ──
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(raw: str) -> str:
    return _pwd.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _pwd.verify(raw, hashed)
    except Exception:
        return False


# ── License token (JWT ký bằng license_secret) ──
_ALGO = "HS256"


def issue_license_token(
    code: str, fingerprint: str, expires_at: datetime | None, plan: str = "standard"
) -> str:
    """
    Sinh license token cho client cache. exp = min(grace_days, license expiry).
    Client chạy offline tới khi token hết hạn thì phải verify lại online.
    Claim `plan` cho phép client biết tier (standard|premium) cả khi offline.
    """
    now = datetime.now(timezone.utc)
    grace_exp = now + timedelta(days=settings.grace_days)
    exp = grace_exp
    if expires_at is not None and expires_at < grace_exp:
        exp = expires_at
    payload = {
        "code": code,
        "fp":   fingerprint,
        "plan": plan or "standard",
        "iat":  int(now.timestamp()),
        "exp":  int(exp.timestamp()),
        "lexp": int(expires_at.timestamp()) if expires_at else 0,  # hạn license thật
    }
    return jwt.encode(payload, settings.license_secret, algorithm=_ALGO)


def decode_license_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.license_secret, algorithms=[_ALGO])
    except jwt.PyJWTError:
        return None


# ── Admin session cookie ──
_session_serializer = URLSafeTimedSerializer(settings.session_secret, salt="admin-session")
SESSION_COOKIE = "qls_admin"
SESSION_MAX_AGE = 8 * 3600  # 8 giờ


def make_session(username: str) -> str:
    return _session_serializer.dumps({"u": username})


def read_session(cookie: str | None) -> str | None:
    if not cookie:
        return None
    try:
        data = _session_serializer.loads(cookie, max_age=SESSION_MAX_AGE)
        return data.get("u")
    except BadSignature:
        return None
    except Exception:
        return None


# ── Helpers ──
def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def rollout_bucket(fingerprint: str) -> int:
    """Map fingerprint → 0..99 ổn định, để rollout theo % không đổi giữa các lần check."""
    h = hashlib.sha256(fingerprint.encode("utf-8", errors="replace")).hexdigest()
    return int(h[:8], 16) % 100
