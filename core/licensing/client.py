"""
Client HTTP cho server license (stdlib urllib). Quản lý token cache trong
activation.json + offline grace.

Cache keys (merge vào activation.json):
  license_code        : mã đã kích hoạt
  license_token       : JWT server cấp (client KHÔNG verify chữ ký — không có secret)
  device_fingerprint  : fingerprint máy lúc kích hoạt
  grace_until_ts      : epoch — hết hạn này mà chưa verify online lại → cần kích hoạt lại
  license_expires_ts  : epoch — hạn license thật (0 = vĩnh viễn)
  last_verify_ts      : epoch — lần verify online gần nhất
"""
import base64
import json
import logging
import time
import urllib.error
import urllib.request

from core.config import ACTIVATION_FILE, AppConfig
from core.licensing.device import device_info, get_fingerprint
from core.version import __version__

log = logging.getLogger(__name__)

_TIMEOUT = 10


# ── Cấu hình server ──
def server_url() -> str:
    return str(AppConfig.get("license_server_url", "") or "").rstrip("/")


def server_configured() -> bool:
    return bool(server_url())


# ── Cache (activation.json) ──
def _load() -> dict:
    try:
        with open(ACTIVATION_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(updates: dict) -> None:
    data = _load()
    data.update(updates)
    try:
        with open(ACTIVATION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log.warning("Không lưu được license cache: %s", e)


def _decode_jwt_claims(token: str) -> dict:
    """Đọc payload JWT KHÔNG verify chữ ký (chỉ để lấy exp/lexp hiển thị + grace)."""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)  # pad base64
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}


def _store_from_response(code: str, fingerprint: str, body: dict) -> None:
    token = body.get("token") or ""
    claims = _decode_jwt_claims(token)
    _save({
        "license_code": code,
        "license_token": token,
        "device_fingerprint": fingerprint,
        "grace_until_ts": int(claims.get("exp", 0)),
        "license_expires_ts": int(claims.get("lexp", 0)),
        "last_verify_ts": int(time.time()),
    })


# ── HTTP ──
def _post(path: str, payload: dict) -> tuple[int, dict]:
    url = f"{server_url()}{path}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": f"QuangLuuStudio/{__version__}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}
    except Exception as e:  # network down
        log.info("License server unreachable: %s", e)
        return 0, {}


# ── API công khai ──
def activate_online(code: str) -> dict:
    """
    Kích hoạt online + ràng máy. Trả {success, error, days_remaining}.
    """
    code = code.strip().upper()
    fp = get_fingerprint()
    info = device_info()
    status, body = _post("/api/v1/activate", {
        "code": code,
        "device_fingerprint": fp,
        "hostname": info["hostname"],
        "os": info["os"],
        "app_version": __version__,
    })

    if status == 0:
        return {"success": False, "error": "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại."}
    if status == 200 and body.get("valid"):
        _store_from_response(code, fp, body)
        return {"success": True, "error": "", "days_remaining": body.get("days_remaining")}
    return {"success": False, "error": body.get("message", "Mã không hợp lệ.")}


def verify_online() -> dict:
    """
    Check-in: xác nhận license còn hiệu lực. Cập nhật grace nếu thành công.
    Trả {success, status, error}. status: active|revoked|expired|invalid|offline.
    """
    cache = _load()
    token = cache.get("license_token")
    code = cache.get("license_code")
    fp = get_fingerprint()
    if not (token or code):
        return {"success": False, "status": "invalid", "error": "Chưa kích hoạt online."}

    status, body = _post("/api/v1/license/verify", {
        "token": token,
        "code": code,
        "device_fingerprint": fp,
        "app_version": __version__,
    })

    if status == 0:
        return {"success": False, "status": "offline", "error": "Không kết nối được máy chủ."}
    if status == 200 and body.get("valid"):
        _store_from_response(code, fp, body)
        return {"success": True, "status": "active", "error": ""}
    return {"success": False, "status": body.get("status", "invalid"), "error": body.get("message", "")}


# ── Trạng thái cho ActivationManager (offline-aware) ──
def has_online_license() -> bool:
    return bool(_load().get("license_token"))


def is_grace_valid() -> bool:
    """Còn trong cửa sổ grace (verify online gần đây) và license chưa hết hạn."""
    cache = _load()
    now = time.time()
    grace_until = cache.get("grace_until_ts", 0)
    lic_exp = cache.get("license_expires_ts", 0)
    if grace_until and now >= grace_until:
        return False
    if lic_exp and now >= lic_exp:
        return False
    return bool(cache.get("license_token"))


def license_expires_ts() -> int:
    return int(_load().get("license_expires_ts", 0))


def days_remaining() -> int:
    exp = license_expires_ts()
    if not exp:
        return 9999  # vĩnh viễn
    return max(0, int((exp - time.time()) / 86400))
