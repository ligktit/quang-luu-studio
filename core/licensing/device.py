"""
Sinh device fingerprint ổn định cho 1 máy Windows.

v2 (hiện hành): CHỈ dùng MachineGuid (HKLM\\SOFTWARE\\Microsoft\\Cryptography).
Ổn định — không đổi khi cài lại app, chỉ đổi khi cài lại Windows.

v1 (cũ, chỉ còn dùng để nhận diện máy đang chạy bản trước): MachineGuid + MAC +
tên máy + CPU. Ba thành phần sau KHÔNG ổn định:
  - uuid.getnode() lấy MAC của một card mạng bất kỳ. Máy có Wi-Fi + LAN +
    Bluetooth PAN + VPN/VirtualBox thì giá trị đổi giữa các lần chạy; cắm/rút
    USB Wi-Fi hoặc dock cũng đổi; Windows 11 bật "địa chỉ phần cứng ngẫu nhiên"
    cho Wi-Fi lại càng đổi. Không lấy được MAC nào thì Python trả về SỐ NGẪU
    NHIÊN mới mỗi lần chạy.
  - platform.node() đổi khi đổi tên máy hoặc join domain.
Hệ quả đã đo được trên production: cùng một máy sinh nhiều fingerprint → server
đếm thành nhiều thiết bị → "đã đạt giới hạn thiết bị" → hỗ trợ reset → máy cũ bị
chặn vĩnh viễn. Client gửi kèm legacy_fingerprint() để server nối lại hai danh
tính. Xem docs/LICENSING_KICKOUT_FIX_PLAN.md.

Tất cả băm SHA256 → chuỗi hex 64 ký tự. Không lộ thông tin gốc.
"""
import hashlib
import logging
import os
import platform
import uuid

log = logging.getLogger(__name__)

_cached: str | None = None
_cached_legacy: str | None = None


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


def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def legacy_fingerprint() -> str:
    """
    Fingerprint theo công thức CŨ (client ≤1.6.2). Chỉ dùng để gửi kèm cho server
    nhận ra máy này là máy đã kích hoạt trước đây — KHÔNG dùng làm danh tính mới.
    """
    global _cached_legacy
    if _cached_legacy:
        return _cached_legacy

    parts = [
        _machine_guid(),
        f"{uuid.getnode():012x}",          # MAC — không ổn định, xem docstring module
        platform.node(),                    # hostname
        os.environ.get("PROCESSOR_IDENTIFIER", ""),
    ]
    _cached_legacy = _sha256("|".join(p for p in parts if p))
    return _cached_legacy


def get_fingerprint() -> str:
    """Trả fingerprint sha256 (hex, 64 ký tự), cache trong process.

    Máy đọc được MachineGuid (mọi bản Windows bình thường) dùng v2. Máy không
    đọc được (thiếu quyền registry, môi trường lạ) rơi về công thức cũ — thà kém
    ổn định còn hơn cả đội hình dồn về một fingerprint chung.
    """
    global _cached
    if _cached:
        return _cached

    guid = _machine_guid()
    if guid:
        _cached = _sha256(f"v2|{guid}")
    else:
        log.warning("Không đọc được MachineGuid — dùng fingerprint công thức cũ")
        _cached = legacy_fingerprint()
    return _cached


def device_info() -> dict:
    """Thông tin máy gửi kèm khi activate (để admin nhận diện)."""
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
    }
