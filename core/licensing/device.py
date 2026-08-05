"""
Sinh device fingerprint ổn định cho 1 máy Windows.

Fingerprint là DANH TÍNH của máy trước server license, nên phải cố định suốt
đời máy. Bản trước băm gộp MachineGuid + MAC + hostname + PROCESSOR_IDENTIFIER;
ba thành phần sau trôi trong sinh hoạt bình thường (bật VPN, cắm dock, Windows
xoay MAC Wi-Fi, đổi tên máy). Khi fingerprint trôi, server coi đây là máy lạ →
/license/verify trả not_activated → hết grace thì app đá user ra → nhập lại mã
thì bản ghi Device cũ vẫn giữ slot nên server báo "đã đạt giới hạn thiết bị".

Chiến lược hiện tại, theo thứ tự ưu tiên:
  1. Fingerprint đã lưu trong activation.json → dùng lại NGUYÊN VĂN. Đây cũng là
     đường phục hồi cho máy đang kẹt: nó lấy lại đúng danh tính lúc kích hoạt.
  2. Chưa có → tính từ MachineGuid (registry), giá trị chỉ đổi khi cài lại
     Windows. Không trộn thêm tín hiệu biến động nào.
  3. Không đọc được registry → sinh install_id ngẫu nhiên một lần rồi lưu lại.

`fingerprint_guid` (hash của MachineGuid) đi kèm để chặn việc bê activation.json
sang máy khác dùng ké slot. Guard vắng mặt (file do bản cũ ghi) thì vẫn chấp
nhận cache — ưu tiên phục hồi cho máy đang lỗi.

Mọi giá trị đều băm SHA256 → hex 64 ký tự, không lộ thông tin gốc.
"""
import hashlib
import json
import logging
import platform
import uuid

from core.config import ACTIVATION_FILE

log = logging.getLogger(__name__)

_cached: str | None = None

_HEX = "0123456789abcdef"


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


# ── activation.json (đọc/ghi tối thiểu; client.py giữ bản riêng để tránh
#    import vòng — client đã import module này) ──
def _read_cache() -> dict:
    try:
        with open(ACTIVATION_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _merge_cache(updates: dict) -> None:
    data = _read_cache()
    data.update(updates)
    try:
        with open(ACTIVATION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log.warning("Không lưu được device fingerprint: %s", e)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _looks_like_fingerprint(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in _HEX for c in value.lower())
    )


def _cache_belongs_to_this_machine(cache: dict, guid: str) -> bool:
    """Guard chống copy activation.json sang máy khác.

    Thiếu guard (file bản cũ) hoặc lần chạy này không đọc được registry →
    chấp nhận. Nghi ngờ registry KHÔNG được phép làm đổi danh tính máy.
    """
    guard = cache.get("fingerprint_guid")
    if not guard or not guid:
        return True
    return guard == _sha256(guid)


def _install_id(cache: dict) -> str:
    """ID ngẫu nhiên lưu trên đĩa — chỉ dùng khi không có MachineGuid."""
    existing = cache.get("install_id")
    if isinstance(existing, str) and existing:
        return existing
    new_id = uuid.uuid4().hex
    _merge_cache({"install_id": new_id})
    return new_id


def get_fingerprint() -> str:
    """Trả fingerprint sha256 (hex, 64 ký tự). Cache trong process lẫn trên đĩa."""
    global _cached
    if _cached:
        return _cached

    cache = _read_cache()
    guid = _machine_guid()

    stored = cache.get("device_fingerprint")
    if _looks_like_fingerprint(stored) and _cache_belongs_to_this_machine(cache, guid):
        _cached = stored
        return _cached

    seed = f"guid:{guid}" if guid else f"install:{_install_id(cache)}"
    _cached = _sha256(seed)

    updates = {"device_fingerprint": _cached}
    if guid:
        updates["fingerprint_guid"] = _sha256(guid)
    _merge_cache(updates)
    return _cached


def device_info() -> dict:
    """Thông tin máy gửi kèm khi activate (để admin nhận diện)."""
    return {
        "hostname": platform.node(),
        "os": f"{platform.system()} {platform.release()}",
    }
