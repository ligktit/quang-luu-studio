"""
core.licensing — kích hoạt online + khoá theo máy, có offline grace.

Chỉ dùng stdlib (urllib, hashlib, pow) để không thêm dependency cho client —
kể cả việc xác minh chữ ký RS256 của license token (xem jwt_verify.py).

Kích hoạt LUÔN đi qua server: không còn nhánh checksum cục bộ nào, nên trong
file exe không còn secret nào để rút ra và tự sinh mã.
"""
from core.licensing.client import (
    activate_online,
    cached_code,
    clear_license_cache,
    days_since_verify,
    in_license_term,
    server_configured,
    server_url,
    start_trial_online,
    startup_reconcile,
    verified_claims,
    verify_online,
)
from core.licensing.device import get_fingerprint

__all__ = [
    "activate_online",
    "verify_online",
    "startup_reconcile",
    "start_trial_online",
    "clear_license_cache",
    "cached_code",
    "days_since_verify",
    "in_license_term",
    "verified_claims",
    "server_configured",
    "server_url",
    "get_fingerprint",
]
