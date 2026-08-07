"""
Bảo mật: license token (JWT), hash mật khẩu admin, session cookie admin, rate-limit.
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from itsdangerous import BadSignature, URLSafeTimedSerializer
from passlib.context import CryptContext
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

log = logging.getLogger(__name__)

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


# ── License token (JWT ký RS256 bằng private key RSA) ──
_ALGO = "RS256"
_LEGACY_ALGO = "HS256"

_MISSING_KEY_HINT = (
    "Chưa cấu hình khoá ký license. Sinh bằng:\n"
    "    python -m app.cli gen-license-keys\n"
    "rồi đặt LICENSE_PRIVATE_KEY (PEM) vào .env, hoặc trỏ "
    "LICENSE_PRIVATE_KEY_PATH tới file .pem."
)


@lru_cache(maxsize=1)
def _private_key():
    """Nạp private key RSA một lần. Raise nếu chưa cấu hình — server license
    không được phép chạy ở chế độ 'ký bằng khoá mặc định'."""
    pem = (settings.license_private_key or "").strip()
    if not pem:
        path = Path(settings.license_private_key_path)
        if path.is_file():
            pem = path.read_text(encoding="utf-8").strip()
    if not pem:
        raise RuntimeError(_MISSING_KEY_HINT)
    # PEM dán vào .env thường bị nuốt xuống dòng — khôi phục lại '\n'.
    pem = pem.replace("\\n", "\n")
    return serialization.load_pem_private_key(pem.encode("utf-8"), password=None)


@lru_cache(maxsize=1)
def _public_key():
    return _private_key().public_key()


def license_public_key_pem() -> str:
    return _public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def license_public_modulus_hex() -> str:
    """Modulus hex HOA — giá trị nhúng vào core/licensing/jwt_verify.py của client."""
    n = _public_key().public_numbers().n
    return f"{n:X}"


def check_signing_key_ready() -> None:
    """Gọi lúc khởi động để chết sớm với thông báo rõ, thay vì lỗi 500 lúc kích hoạt."""
    _private_key()


def issue_license_token(
    code: str, fingerprint: str, expires_at: datetime | None, plan: str = "standard"
) -> str:
    """
    Sinh license token cho client cache. exp = min(grace_days, license expiry).
    Client chạy offline tới khi token hết hạn thì phải verify lại online.
    Claim `plan` cho phép client biết tier (standard|premium) cả khi offline —
    và vì token ký RS256, client tự xác minh được là plan không bị sửa tay.
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
    return jwt.encode(payload, _private_key(), algorithm=_ALGO)


def decode_license_token(token: str) -> dict | None:
    """
    Đọc token client gửi lên. Nhận RS256 (hiện hành) và HS256 (token cũ, chỉ khi
    LICENSE_SECRET còn được cấu hình) để máy chưa cập nhật vẫn check-in được —
    lần check-in đó sẽ trả về token RS256 mới.
    """
    try:
        return jwt.decode(token, _public_key(), algorithms=[_ALGO])
    except jwt.PyJWTError:
        pass

    legacy_secret = (settings.license_secret or "").strip()
    if legacy_secret:
        try:
            claims = jwt.decode(token, legacy_secret, algorithms=[_LEGACY_ALGO])
            log.info("Chấp nhận token HS256 cũ của mã %s — sẽ cấp lại token RS256",
                     claims.get("code"))
            return claims
        except jwt.PyJWTError:
            pass
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
