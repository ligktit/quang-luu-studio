"""
Sinh device fingerprint ổn định cho 1 máy Windows.

Kết hợp:
  - MachineGuid (registry HKLM\\SOFTWARE\\Microsoft\\Cryptography) — ổn định, không
    đổi khi reinstall app, chỉ đổi khi cài lại Windows.
  - MAC address (uuid.getnode) — phụ trợ.
  - Tên máy + processor — phụ trợ.
Tất cả băm SHA256 → chuỗi hex 64 ký tự. Không lộ thông tin gốc.
"""
import hashlib
import logging
import os
import platform
import uuid

log = logging.getLogger(__name__)

_cached: str | None = None


def _machine_guid() -> str:
    """Đọc MachineGuid từ registry Windows. Rỗng nếu không lấy được."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        try:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
        finally:
            winreg.CloseKey(key)
    except Exception as e:  # noqa: BLE001 — non-Windows hoặc thiếu quyền
        log.debug("MachineGuid unavailable: %s", e)
        return ""


def get_fingerprint() -> str:
    """Trả fingerprint sha256 (hex, 64 ký tự), cache trong process."""
    global _cached
    if _cached:
        return _cached

    parts = [
        _machine_guid(),
        f"{uuid.getnode():012x}",          # MAC
        platform.node(),                    # hostname
        os.environ.get("PROCESSOR_IDENTIFIER", ""),
    ]
    raw = "|".join(p for p in parts if p)
    _cached = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
    return _cached


def device_info() -> dict:
    """Thông tin máy gửi kèm khi activate (để admin nhận diện)."""
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
    }
