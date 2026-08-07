"""
tools/set_test_premium.py  —  CHỈ DÙNG ĐỂ TEST UI PREMIUM (DEV)
==============================================================
Bật gói Premium trên MÁY NÀY bằng cách ký một license token thật, đúng định dạng
mà app dùng ngoài đời (RS256, ràng theo fingerprint máy).

Bản cũ của script này bịa một token không chữ ký — client hồi đó không kiểm chữ
ký nên vẫn nuốt. Giờ client xác minh RS256 bằng public key nhúng sẵn, nên muốn
bật Premium thủ công BẮT BUỘC phải có private key của server. Đó là chủ ý: nếu
script này chạy được mà không cần khoá, thì người dùng cuối cũng làm được vậy.

Dùng:
    python tools/set_test_premium.py --key path/to/license_key.pem   # BẬT
    python tools/set_test_premium.py --off                            # TẮT
    python tools/set_test_premium.py --status                         # xem trạng thái

Cần `cryptography` trong môi trường dev (KHÔNG nằm trong requirements.txt của
app vì bản build không cần ký, chỉ cần xác minh):
    pip install cryptography

Tự backup activation.json (.bak) trước khi sửa.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.config import ACTIVATION_FILE  # noqa: E402

TEST_CODE = "TEST-PREM-IUM0-DEV0-0001"
_CACHE_KEYS = ("license_code", "license_token", "device_fingerprint", "last_verify_ts")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _sign_token(key_path: str, fingerprint: str, plan: str, exp: int, lexp: int) -> str:
    """Ký JWT RS256 đúng cách bằng private key của server."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        raise SystemExit("Thiếu thư viện: pip install cryptography")

    with open(key_path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)

    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64url(json.dumps({
        "code": TEST_CODE, "fp": fingerprint, "plan": plan,
        "iat": int(time.time()), "exp": exp, "lexp": lexp,
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{payload}.{_b64url(signature)}"


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_json(path: str, data: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _backup(path: str):
    if os.path.exists(path) and not os.path.exists(path + ".bak"):
        shutil.copy2(path, path + ".bak")


def enable(key_path: str):
    from core.licensing.device import get_fingerprint

    if not os.path.isfile(key_path):
        raise SystemExit(f"Không thấy private key: {key_path}\n"
                         "Sinh bằng: python -m app.cli gen-license-keys (trong thư mục server/)")

    fingerprint = get_fingerprint()
    now = int(time.time())
    horizon = now + 365 * 24 * 3600
    token = _sign_token(key_path, fingerprint, "premium", horizon, horizon)

    _backup(ACTIVATION_FILE)
    act = _read_json(ACTIVATION_FILE)
    act.update({
        "license_code": TEST_CODE,
        "license_token": token,
        "device_fingerprint": fingerprint,
        "last_verify_ts": now,
    })
    _write_json(ACTIVATION_FILE, act)

    print("✅ ĐÃ BẬT Premium (test).")
    print(f"   activation.json : {ACTIVATION_FILE}")
    print(f"   fingerprint máy : {fingerprint[:16]}…")
    _print_status()


def disable():
    act = _read_json(ACTIVATION_FILE)
    for k in _CACHE_KEYS:
        act.pop(k, None)
    _write_json(ACTIVATION_FILE, act)
    print("↩️  ĐÃ TẮT Premium test — đã xoá license cache.")
    _print_status()


def _print_status():
    try:
        from core import entitlements
        from core.licensing import client as lic
        lic._claims_memo = ("", None)  # bỏ memo trong process để đọc lại file
        print(f"   → entitlements.current_plan() = {entitlements.current_plan()!r}")
        print(f"   → entitlements.is_premium()   = {entitlements.is_premium()}")
    except Exception as e:
        print(f"   (không kiểm tra được entitlements: {e})")


def main():
    ap = argparse.ArgumentParser(description="Bật/tắt Premium để TEST UI (dev).")
    ap.add_argument("--key", help="Đường dẫn private key RSA của server license")
    ap.add_argument("--off", action="store_true", help="Tắt premium test")
    ap.add_argument("--status", action="store_true", help="Chỉ xem trạng thái")
    args = ap.parse_args()

    if args.status:
        _print_status()
    elif args.off:
        disable()
    elif args.key:
        enable(args.key)
    else:
        ap.error("cần --key <license_key.pem> để bật (xem hướng dẫn ở đầu file)")


if __name__ == "__main__":
    main()
