"""
Quang Lưu Studio — Khoá kỹ thuật ("Chế độ khách").

Mục tiêu: khách hàng phổ thông không thấy và không chạm được vào Studio One;
chỉ nhân viên kỹ thuật mở được bằng mã PIN.

Trạng thái nằm trong settings.json → key "tech_lock":

    {
      "enabled": true,            # đang khoá (chế độ khách)
      "pin_salt": "<hex 16 byte>",
      "pin_hash": "<hex>",        # PBKDF2-HMAC-SHA256
      "iterations": 260000,
      "keep_hidden": false,       # watchdog nền ẩn lại MỌI cửa sổ Studio One
      "session_minutes": 20,      # phiên kỹ thuật tự khoá lại sau bấy nhiêu phút
      "restore_template": true    # phục hồi bản mẫu .song mỗi lần khởi động
    }

PIN lưu dạng băm PBKDF2 + salt ngẫu nhiên — đọc file cũng không lấy lại được PIN.
Không có cửa hậu: quên PIN thì phải xoá key "tech_lock" trong settings.json
(nằm ở %APPDATA%\\QuangLuuStudio — khách hàng phổ thông không mò tới).

Phiên kỹ thuật CHỈ tồn tại trong RAM: đóng app là khoá lại, không thể "quên tắt"
qua đêm. Hết `session_minutes` cũng tự khoá.
"""
import hashlib
import hmac
import logging
import os
import time

log = logging.getLogger(__name__)

_KEY = "tech_lock"
_ITERATIONS = 260_000
_DEFAULT_SESSION_MINUTES = 20
_MIN_PIN_LEN = 4
_MAX_PIN_LEN = 32

# Chống dò PIN: sai 5 lần → nghỉ 60s, mỗi mốc 5 lần tiếp theo nhân đôi (tối đa 15').
_FAIL_THRESHOLD = 5
_FAIL_BASE_COOLDOWN = 60
_FAIL_MAX_COOLDOWN = 900

# ── Trạng thái RAM (không bao giờ ghi ra đĩa) ─────────────────────────────────
_live_settings = None
_session_until = 0.0          # time.monotonic() hết hạn phiên kỹ thuật; 0 = không có phiên
_fail_count = 0
_lockout_until = 0.0


# ── Đọc/ghi cấu hình ─────────────────────────────────────────────────────────

def bind(settings):
    """Gắn dict settings đang sống của app.

    Dashboard giữ `self.settings` trong RAM và ghi đè cả file lúc thoát; nếu
    module này chỉ ghi thẳng xuống đĩa thì thay đổi sẽ bị bản cũ trong RAM xoá
    mất. Gắn ở đây để mọi thay đổi vá vào cả hai nơi.
    """
    global _live_settings
    _live_settings = settings if isinstance(settings, dict) else None


def _cfg():
    if _live_settings is not None:
        cfg = _live_settings.get(_KEY)
        return dict(cfg) if isinstance(cfg, dict) else {}
    try:
        from core.config import ConfigManager
        cfg = (ConfigManager.load_settings() or {}).get(_KEY)
        return dict(cfg) if isinstance(cfg, dict) else {}
    except Exception as e:  # pragma: no cover — phòng thủ
        log.debug("kiosk._cfg lỗi: %s", e)
        return {}


def _write(**patch):
    """Vá vài trường vào tech_lock rồi lưu (cả file lẫn dict đang sống)."""
    from core.config import ConfigManager
    disk = ConfigManager.load_settings() or {}
    cfg = dict(disk.get(_KEY) or {})
    cfg.update(patch)
    disk[_KEY] = cfg
    ConfigManager.save_settings(disk)
    if _live_settings is not None:
        _live_settings[_KEY] = cfg
    return cfg


# ── PIN ──────────────────────────────────────────────────────────────────────

def _hash_pin(pin: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations).hex()


def has_pin() -> bool:
    cfg = _cfg()
    return bool(cfg.get("pin_hash")) and bool(cfg.get("pin_salt"))


def set_pin(pin: str):
    """Đặt/đổi PIN. Ném ValueError nếu PIN quá ngắn/quá dài."""
    pin = (pin or "").strip()
    if len(pin) < _MIN_PIN_LEN:
        raise ValueError(f"Mã PIN phải có ít nhất {_MIN_PIN_LEN} ký tự")
    if len(pin) > _MAX_PIN_LEN:
        raise ValueError(f"Mã PIN tối đa {_MAX_PIN_LEN} ký tự")
    salt = os.urandom(16)
    _write(
        pin_salt=salt.hex(),
        pin_hash=_hash_pin(pin, salt, _ITERATIONS),
        iterations=_ITERATIONS,
    )
    reset_failures()


def verify_pin(pin: str) -> bool:
    cfg = _cfg()
    salt_hex = cfg.get("pin_salt")
    stored = cfg.get("pin_hash")
    if not salt_hex or not stored:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    iterations = int(cfg.get("iterations") or _ITERATIONS)
    candidate = _hash_pin((pin or "").strip(), salt, iterations)
    return hmac.compare_digest(candidate, stored)


# ── Chống dò PIN ─────────────────────────────────────────────────────────────

def lockout_remaining() -> int:
    """Số giây còn phải chờ trước khi được nhập PIN tiếp (0 = nhập được ngay)."""
    return max(0, int(round(_lockout_until - time.monotonic())))


def register_failure() -> int:
    """Ghi nhận 1 lần nhập sai. Trả số giây bị khoá (0 nếu chưa tới ngưỡng)."""
    global _fail_count, _lockout_until
    _fail_count += 1
    if _fail_count % _FAIL_THRESHOLD:
        return 0
    step = _fail_count // _FAIL_THRESHOLD
    cooldown = min(_FAIL_MAX_COOLDOWN, _FAIL_BASE_COOLDOWN * (2 ** (step - 1)))
    _lockout_until = time.monotonic() + cooldown
    log.warning("Nhập sai PIN kỹ thuật %d lần — khoá %ds", _fail_count, cooldown)
    return cooldown


def reset_failures():
    global _fail_count, _lockout_until
    _fail_count = 0
    _lockout_until = 0.0


# ── Bật/tắt khoá ─────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    return bool(_cfg().get("enabled"))


def enable():
    """Bật chế độ khách. Yêu cầu đã đặt PIN — nếu không sẽ tự khoá chính mình."""
    if not has_pin():
        raise ValueError("Phải đặt mã PIN kỹ thuật trước khi bật chế độ khách")
    _write(enabled=True)
    end_session()


def disable():
    _write(enabled=False)
    end_session()


def keep_hidden() -> bool:
    """Có chạy watchdog nền ẩn lại mọi cửa sổ Studio One hay không (mặc định: không)."""
    return bool(_cfg().get("keep_hidden", False))


def set_keep_hidden(value: bool):
    _write(keep_hidden=bool(value))


def restore_template_enabled() -> bool:
    """Có phục hồi bản mẫu .song mỗi lần khởi động hay không (mặc định: có)."""
    return bool(_cfg().get("restore_template", True))


def set_restore_template(value: bool):
    _write(restore_template=bool(value))


# ── Phiên kỹ thuật ───────────────────────────────────────────────────────────

def session_minutes() -> int:
    try:
        return max(1, int(_cfg().get("session_minutes") or _DEFAULT_SESSION_MINUTES))
    except (TypeError, ValueError):
        return _DEFAULT_SESSION_MINUTES


def set_session_minutes(minutes: int):
    _write(session_minutes=max(1, int(minutes)))


def start_session(minutes=None):
    """Mở phiên kỹ thuật. Gọi SAU khi verify_pin() trả True."""
    global _session_until
    mins = session_minutes() if minutes is None else max(1, int(minutes))
    _session_until = time.monotonic() + mins * 60
    reset_failures()
    log.info("Mở phiên kỹ thuật %d phút", mins)


def end_session():
    global _session_until
    if _session_until:
        log.info("Đóng phiên kỹ thuật")
    _session_until = 0.0


def session_active() -> bool:
    return _session_until > time.monotonic()


def session_remaining() -> int:
    """Số giây còn lại của phiên kỹ thuật (0 nếu không có phiên)."""
    return max(0, int(round(_session_until - time.monotonic())))


def is_locked() -> bool:
    """True khi đang ở chế độ khách VÀ không có phiên kỹ thuật hiệu lực.

    Đây là hàm duy nhất UI nên hỏi để quyết định ẩn/hiện thứ gì.
    """
    return is_enabled() and not session_active()
