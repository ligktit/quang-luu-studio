"""Chọn hồ sơ DAW đang dùng (Studio One / Cubase) theo settings["daw_kind"]."""
from core.daw.profiles import CUBASE, DEFAULT_KIND, PROFILES, STUDIO_ONE, DawProfile

__all__ = ["DawProfile", "STUDIO_ONE", "CUBASE", "PROFILES", "DEFAULT_KIND",
           "active", "bind", "is_project_file", "kind_of"]

_live_settings = None


def bind(settings):
    """Gắn dict settings sống của app (None = đọc file mỗi lần)."""
    global _live_settings
    _live_settings = settings if isinstance(settings, dict) else None


def kind_of(settings) -> str:
    kind = (settings or {}).get("daw_kind")
    return kind if kind in PROFILES else DEFAULT_KIND


def active(settings=None) -> DawProfile:
    """Hồ sơ DAW đang chọn. Thiếu/sai daw_kind → Studio One."""
    if settings is None:
        if _live_settings is not None:
            settings = _live_settings
        else:
            try:
                from core.config import ConfigManager
                settings = ConfigManager.load_settings() or {}
            except Exception:
                settings = {}
    return PROFILES[kind_of(settings)]


def is_project_file(path, profile=None) -> bool:
    if not path:
        return False
    profile = profile or active()
    return str(path).lower().endswith(profile.template_extension)
