"""
tools/set_test_premium.py  —  CHỈ DÙNG ĐỂ TEST UI PREMIUM (DEV)
==============================================================
Trong thiết kế thật, "premium" do SERVER cấp (cột License.plan) → token có claim
plan="premium". Mã offline (checksum) KHÔNG mang thông tin gói, nên không thể bật
premium chỉ bằng một chuỗi mã khi chưa dựng server.

Script này MÔ PHỎNG một thiết bị đã kích hoạt gói Premium bằng cách ghi sẵn
license cache vào activation.json (đúng đường mà core/entitlements.is_premium()
đọc) + bật license_server_url để client ở "chế độ online". Không cần chạy server
(các lần verify nền sẽ fail-soft, grace giữ premium tới hạn đặt sẵn).

Dùng:
    python tools/set_test_premium.py          # BẬT premium (test)
    python tools/set_test_premium.py --off     # TẮT, trả lại trial/standard
    python tools/set_test_premium.py --status  # xem trạng thái hiện tại

Tự backup activation.json / app_config.json (.bak) trước khi sửa.
KHÔNG commit file này vào bản phát hành như một đường tắt — đây là công cụ test.
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

from core.config import ACTIVATION_FILE, AppConfig  # noqa: E402

CONFIG_PATH = AppConfig._get_config_path()
PLACEHOLDER_URL = "http://localhost:8799"   # local, không cần chạy thật (fail-soft)
TEST_CODE = "TEST-PREM-IUM0-DEV0-0001"
TEST_FP = "TEST-PREMIUM-DEVICE-0001"


def _b64url(obj: dict) -> str:
    raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _make_token(plan: str, exp: int, lexp: int) -> str:
    """JWT giả lập (client KHÔNG verify chữ ký) — đủ để decode claim plan/exp."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"code": TEST_CODE, "fp": TEST_FP, "plan": plan,
               "iat": int(time.time()), "exp": exp, "lexp": lexp}
    return f"{_b64url(header)}.{_b64url(payload)}.testsignature"


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


def enable():
    now = int(time.time())
    horizon = now + 365 * 24 * 3600   # grace + hạn license: 1 năm
    token = _make_token("premium", horizon, horizon)

    _backup(ACTIVATION_FILE)
    act = _read_json(ACTIVATION_FILE)
    act.update({
        "license_code": TEST_CODE,
        "license_token": token,
        "license_plan": "premium",
        "device_fingerprint": TEST_FP,
        "grace_until_ts": horizon,
        "license_expires_ts": horizon,
        "last_verify_ts": now,
    })
    _write_json(ACTIVATION_FILE, act)

    _backup(CONFIG_PATH)
    cfg = _read_json(CONFIG_PATH)
    cfg["license_server_url"] = PLACEHOLDER_URL
    _write_json(CONFIG_PATH, cfg)

    print("✅ ĐÃ BẬT Premium (test).")
    print(f"   activation.json : {ACTIVATION_FILE}")
    print(f"   app_config.json : {CONFIG_PATH}  (license_server_url={PLACEHOLDER_URL})")
    print(f"   Mã test         : {TEST_CODE}")
    _print_status()


def disable():
    act = _read_json(ACTIVATION_FILE)
    for k in ("license_code", "license_token", "license_plan", "device_fingerprint",
              "grace_until_ts", "license_expires_ts", "last_verify_ts"):
        act.pop(k, None)
    _write_json(ACTIVATION_FILE, act)

    cfg = _read_json(CONFIG_PATH)
    cfg.pop("license_server_url", None)
    _write_json(CONFIG_PATH, cfg)

    print("↩️  ĐÃ TẮT Premium test — trả lại trial/standard (đã xoá license cache + server url).")
    _print_status()


def _print_status():
    try:
        # Reset cache _data của AppConfig — trong cùng process nó cache config cũ
        # (đã đọc trước khi ta ghi file) nên phải nạp lại để báo đúng.
        AppConfig._data = None
        from core import entitlements
        print(f"   → entitlements.current_plan() = {entitlements.current_plan()!r}")
        print(f"   → entitlements.is_premium()   = {entitlements.is_premium()}")
    except Exception as e:
        print(f"   (không kiểm tra được entitlements: {e})")


def main():
    ap = argparse.ArgumentParser(description="Bật/tắt Premium để TEST UI (dev).")
    ap.add_argument("--off", action="store_true", help="Tắt premium test")
    ap.add_argument("--status", action="store_true", help="Chỉ xem trạng thái")
    args = ap.parse_args()

    if args.status:
        _print_status()
    elif args.off:
        disable()
    else:
        enable()


if __name__ == "__main__":
    main()
