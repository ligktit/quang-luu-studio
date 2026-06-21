"""
Sinh & xác thực activation code.

Thuật toán GIỐNG HỆT client cũ (core/activation.py, tools/generate_code.py):
  - Mã: 4 nhóm "AA00" (2 chữ + 2 số) nối '-', cộng 1 nhóm checksum.
  - checksum = md5(base + CODE_SECRET).hexdigest()[:4].upper()
  - Mỗi nhóm (kể cả checksum) phải có cả chữ và số.

Nhờ giữ nguyên thuật toán, mã đã phát hành trước đây vẫn import & verify được.
"""
import hashlib
import random
import string

from app.config import settings

SECRET = settings.code_secret


def _checksum(base_code: str) -> str:
    return hashlib.md5((base_code + SECRET).encode()).hexdigest()[:4].upper()


def generate_code() -> str:
    while True:
        groups = []
        for _ in range(4):
            g = "".join(random.choices(string.ascii_uppercase, k=2))
            g += "".join(random.choices(string.digits, k=2))
            groups.append(g)
        base = "-".join(groups)
        chk = _checksum(base)
        if any(c.isalpha() for c in chk) and any(c.isdigit() for c in chk):
            return f"{base}-{chk}"


def generate_codes(n: int) -> list[str]:
    seen: set[str] = set()
    while len(seen) < n:
        seen.add(generate_code())
    return list(seen)


def validate_structure(code: str) -> bool:
    if not code:
        return False
    parts = code.strip().upper().split("-")
    if len(parts) != 5:
        return False
    for part in parts:
        if len(part) != 4:
            return False
        if not any(c.isalpha() for c in part) or not any(c.isdigit() for c in part):
            return False
    return True


def verify_checksum(code: str) -> bool:
    parts = code.strip().upper().split("-")
    if len(parts) != 5:
        return False
    base = "-".join(parts[:4])
    return parts[4] == _checksum(base)


def is_valid_code(code: str) -> bool:
    return validate_structure(code) and verify_checksum(code)
