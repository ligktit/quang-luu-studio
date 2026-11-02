"""
Quang Lưu Studio — Ẩn cửa sổ DAW (Studio One/Cubase) khỏi khách hát.

Thay cho khoá kỹ thuật (PIN + phiên kỹ thuật) cũ: mỗi lần mở app, các cửa sổ DAW
tự ẩn; KTV hiện lại trong Cài đặt → "Cửa sổ {DAW}".

Trạng thái nằm trong settings.json → key "daw_windows":

    {
      "auto_hide": true,          # tự ẩn DAW khi mở app (và khi app tự mở DAW)
      "restore_template": false   # phục hồi bản mẫu .song/.cpr mỗi lần khởi động
    }

Máy cũ còn key "tech_lock" được chuyển một lần qua migrate(): máy đang bật chế
độ khách giữ việc phục hồi bản mẫu; dữ liệu PIN bị xoá.
"""
import logging

log = logging.getLogger(__name__)

_KEY = "daw_windows"
_OLD_KEY = "tech_lock"
_DEFAULTS = {"auto_hide": True, "restore_template": False}

_live_settings = None


def bind(settings):
    """Gắn dict settings đang sống của app.

    Dashboard giữ `self.settings` trong RAM và ghi đè cả file lúc thoát; chỉ ghi
    xuống đĩa thì thay đổi sẽ bị bản cũ trong RAM xoá mất. Gắn ở đây để mọi thay
    đổi vá vào cả hai nơi.
    """
    global _live_settings
    _live_settings = settings if isinstance(settings, dict) else None


def _cfg() -> dict:
    if _live_settings is not None:
        cfg = _live_settings.get(_KEY)
    else:
        try:
            from core.config import ConfigManager
            cfg = (ConfigManager.load_settings() or {}).get(_KEY)
        except Exception as e:  # pragma: no cover — phòng thủ
            log.debug("daw_visibility._cfg lỗi: %s", e)
            cfg = None
    return dict(cfg) if isinstance(cfg, dict) else {}


def _get(name) -> bool:
    return bool(_cfg().get(name, _DEFAULTS[name]))


def _write(**patch):
    """Vá vài trường vào daw_windows rồi lưu (cả file lẫn dict đang sống)."""
    from core.config import ConfigManager
    disk = ConfigManager.load_settings() or {}
    cfg = disk.get(_KEY)
    cfg = dict(cfg) if isinstance(cfg, dict) else {}
    cfg.update(patch)
    disk[_KEY] = cfg
    ConfigManager.save_settings(disk)
    if _live_settings is not None:
        _live_settings[_KEY] = dict(cfg)
    return cfg


def auto_hide() -> bool:
    return _get("auto_hide")


def set_auto_hide(value: bool):
    _write(auto_hide=bool(value))


def restore_template_enabled() -> bool:
    return _get("restore_template")


def set_restore_template(value: bool):
    _write(restore_template=bool(value))


def migrate(settings: dict) -> bool:
    """Chuyển cấu hình khoá kỹ thuật cũ sang daw_windows. Sửa dict tại chỗ.

    Trả True nếu có thay đổi (caller lưu xuống đĩa).
    """
    changed = False
    if not isinstance(settings.get(_KEY), dict):
        old = settings.get(_OLD_KEY)
        old = old if isinstance(old, dict) else {}
        restore = bool(old.get("enabled")) and bool(old.get("restore_template", True))
        settings[_KEY] = {"auto_hide": True, "restore_template": restore}
        changed = True
    if _OLD_KEY in settings:
        del settings[_OLD_KEY]
        changed = True
    return changed
