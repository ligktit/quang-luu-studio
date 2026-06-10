"""
Quang Lưu Studio — Configuration Management
Classes: AppConfig, ConfigManager
Constants: SETTINGS_FILE, SONGS_FILE, ACTIVATION_FILE, etc.

File path convention:
  - USER DATA (writable): %APPDATA%/QuangLuuStudio/
    → settings.json, saved_songs.json, activation.json,
      tone_cache.json, manual_timelines.json
  - APP CONFIG (read-only, admin editable): next to EXE
    → app_config.json
  - RECORDINGS: Documents/QuangLuuStudio/
"""
import os
import sys
import json
import copy

from core.utils import find_ffmpeg


# ── Path Helpers ─────────────────────────────────────────

def _get_app_dir():
    """Thư mục chứa EXE (frozen) hoặc project root (dev).
    Dùng cho file read-only: app_config.json, sfx/, studio_one/"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_data_dir():
    """Thư mục dữ liệu user: %APPDATA%/QuangLuuStudio/ (frozen)
    hoặc project root (dev). Tự tạo nếu chưa có.
    Dùng cho: settings, songs, activation, tone_cache, timelines"""
    if getattr(sys, 'frozen', False):
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        data_dir = os.path.join(base, 'QuangLuuStudio')
    else:
        # Dev mode: giữ nguyên cạnh source code để tiện debug
        data_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def _get_recordings_dir():
    """Thư mục recordings: Documents/QuangLuuStudio/ (frozen)
    hoặc temp_audio/ (dev). Tự tạo nếu chưa có."""
    if getattr(sys, 'frozen', False):
        docs = os.path.join(os.path.expanduser('~'), 'Documents')
        rec_dir = os.path.join(docs, 'QuangLuuStudio')
    else:
        rec_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'temp_audio'
        )
    os.makedirs(rec_dir, exist_ok=True)
    return rec_dir


# ── Derived Paths ────────────────────────────────────────
APP_DIR = _get_app_dir()
DATA_DIR = _get_data_dir()
RECORDINGS_DIR = _get_recordings_dir()

# --- CẤU HÌNH CỐT LÕI (user-writable → DATA_DIR) ---
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
SONGS_FILE = os.path.join(DATA_DIR, "saved_songs.json")
ACTIVATION_FILE = os.path.join(DATA_DIR, "activation.json")
MANUAL_TIMELINES_FILE = os.path.join(DATA_DIR, "manual_timelines.json")
TONE_CACHE_FILE = os.path.join(DATA_DIR, "tone_cache.json")
UI_CONFIG_FILE = os.path.join(DATA_DIR, "ui_config.json")

# --- APP CONFIG (read-only, nằm cạnh exe → APP_DIR) ---
APP_CONFIG_FILE = "app_config.json"

# Defaults nếu file không tồn tại hoặc thiếu field
_DEFAULT_APP_CONFIG = {
    "midi_port_name": "QuangLuuMIDI",
    "youtube_cookie_browser": "auto",
    "youtube_cookie_profile": "",
    "youtube_cookie_file": "",
    "midi_cc": {
        "tone_music": 10, "tone_voice": 11,
        "mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "mix_backing": 23,
        "mode": 30, "autokey": 31, "score_trigger": 32,
        "key_root": 33, "key_scale": 34, "scale_type": 35,
        "tune_on_off": 36, "tone_auto": 31, "fix_meo": 36,
        "mode_danca": 30, "mode_lofi": 37, "mode_remix": 38, "mode_datheloai": 39,
        "mute_music": 50, "mute_mic": 51, "mute_reverb": 52, "mute_backing": 53,
    },
    "scale_values": {
        "major": 13,
        "minor": 18
    },
    "key_midi_map": {
        "C": 0, "C#": 11, "Db": 11, "D": 23, "D#": 34, "Eb": 34,
        "E": 46, "F": 57, "F#": 69, "G": 80,
        "G#": 92, "Ab": 92, "A": 103, "A#": 115, "Bb": 115, "B": 127,
    },
    "scale_midi_map": {
        "Major": 13,
        "Minor": 18
    },
    "mode_midi_map": {
        "Fix Méo": 127
    },
    "mode_config": {
        "Dân Ca":       {"cc": 30, "on_value": 127, "off_value": 0},
        "Lofi":         {"cc": 37, "on_value": 127, "off_value": 0},
        "Remix":        {"cc": 38, "on_value": 127, "off_value": 0},
        "Đa Thể Loại":  {"cc": 39, "on_value": 127, "off_value": 0}
    },
    "mute_multi_cc": {
        "mix_music":   [],
        "mix_mic":     [],
        "mix_reverb":  [
            {"cc": 41, "on_value": 127, "off_value": 0}
        ],
        "mix_backing": []
    },
    "accessibility": {
        "tts_enabled": False,
        "tts_voice": "",
        "tts_rate": 180,
        "voice_command_enabled": False,
        "voice_command_hotkey": "Ctrl+Space",
        "high_contrast": False,
        "font_scale": 1.0,
        "focus_ring_thick": False,
        "announce_focus": True,
        "announce_state": True
    }
}


class AppConfig:
    """
    Singleton đọc app_config.json từ thư mục chứa exe (frozen) hoặc source (dev).
    Sửa file JSON bằng Notepad → restart app → có hiệu lực, KHÔNG cần build lại exe.
    """
    _instance = None
    _data = None

    @classmethod
    def _get_config_path(cls):
        """Tìm đường dẫn app_config.json — nằm cạnh exe (read-only)"""
        return os.path.join(APP_DIR, APP_CONFIG_FILE)

    @classmethod
    def load(cls):
        """Load config từ file, merge với defaults"""
        if cls._data is not None:
            return cls._data

        cls._data = copy.deepcopy(_DEFAULT_APP_CONFIG)
        config_path = cls._get_config_path()

        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)

                # Merge: user config ghi đè defaults
                for key, value in user_config.items():
                    if isinstance(value, dict) and key in cls._data and isinstance(cls._data[key], dict):
                        cls._data[key].update(value)
                    else:
                        cls._data[key] = value

                import logging
                logging.getLogger("config").info(f"App config loaded: {config_path}")
            except Exception as e:
                import logging
                logging.getLogger("config").warning(f"Lỗi đọc {APP_CONFIG_FILE}: {e} — dùng giá trị mặc định")
        else:
            import logging
            logging.getLogger("config").info(f"{APP_CONFIG_FILE} không tìm thấy — dùng giá trị mặc định")

        return cls._data

    @classmethod
    def get(cls, key, default=None):
        """Lấy giá trị config theo key"""
        data = cls.load()
        return data.get(key, default)

    @classmethod
    def get_midi_cc(cls):
        """Lấy MIDI CC mapping dict"""
        return cls.load().get("midi_cc", _DEFAULT_APP_CONFIG["midi_cc"])

    @classmethod
    def get_scale_values(cls):
        """Lấy scale values dict"""
        return cls.load().get("scale_values", _DEFAULT_APP_CONFIG["scale_values"])

    @classmethod
    def get_key_midi_map(cls):
        """Lấy Key → MIDI CC value mapping (cho Auto-Tune plugin)"""
        return cls.load().get("key_midi_map", _DEFAULT_APP_CONFIG["key_midi_map"])

    @classmethod
    def get_scale_midi_map(cls):
        """Lấy Scale → MIDI CC value mapping (cho Auto-Tune plugin)"""
        return cls.load().get("scale_midi_map", _DEFAULT_APP_CONFIG["scale_midi_map"])

    @classmethod
    def get_mode_midi_map(cls):
        """Lấy Mode → MIDI CC value mapping (cho Auto-Tune plugin)"""
        return cls.load().get("mode_midi_map", _DEFAULT_APP_CONFIG["mode_midi_map"])

    @classmethod
    def get_mode_config(cls):
        """Lấy cấu hình MIDI chi tiết của các chế độ (CC, on_value, off_value)"""
        return cls.load().get("mode_config", _DEFAULT_APP_CONFIG["mode_config"])

    @classmethod
    def get_accessibility(cls):
        """Lấy accessibility config (TTS, voice command, theme...)."""
        return cls.load().get("accessibility", _DEFAULT_APP_CONFIG["accessibility"])

    @classmethod
    def set_accessibility(cls, **kwargs):
        """Cập nhật một hoặc nhiều field accessibility và lưu file."""
        data = cls.load()
        a11y = data.setdefault("accessibility", dict(_DEFAULT_APP_CONFIG["accessibility"]))
        a11y.update(kwargs)
        cls.save()

    @classmethod
    def get_mute_multi_cc(cls):
        """Lấy danh sách MIDI CC phụ gửi kèm khi toggle mute cho từng kênh.
        
        Returns dict: {cc_key: [{cc, on_value, off_value}, ...]}
        VD: kênh mix_reverb có thể gửi thêm CC 41 (toggle vang hiệu ứng).
        Cấu hình trong app_config.json, key "mute_multi_cc".
        """
        return cls.load().get("mute_multi_cc", _DEFAULT_APP_CONFIG["mute_multi_cc"])

    @classmethod
    def reload(cls):
        """Force reload config từ file (VD: sau khi user sửa file)"""
        cls._data = None
        return cls.load()

    @classmethod
    def update(cls, key, value):
        """Cập nhật một key trong config (merge nếu là dict)"""
        data = cls.load()
        if isinstance(value, dict) and key in data and isinstance(data[key], dict):
            data[key].update(value)
        else:
            data[key] = value

    @classmethod
    def save(cls):
        """Ghi config hiện tại ra file app_config.json"""
        if cls._data is None:
            return False
        config_path = cls._get_config_path()
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cls._data, f, indent=4, ensure_ascii=False)
            print(f"App config saved: {config_path}")
            return True
        except Exception as e:
            print(f"Lỗi ghi {APP_CONFIG_FILE}: {e}")
            return False


# Load config ngay khi import module
AppConfig.load()
MIDI_PORT_NAME = AppConfig.get("midi_port_name", "QuangLuuMIDI")

# FFmpeg location (sử dụng consolidated find_ffmpeg từ core.utils)
FFMPEG_LOCATION = find_ffmpeg()
if FFMPEG_LOCATION:
    import logging
    logging.getLogger("config").info(f"FFmpeg found: {FFMPEG_LOCATION}")
    # Thêm vào PATH để yt-dlp download_ranges có thể tìm ffmpeg
    if FFMPEG_LOCATION not in os.environ.get("PATH", ""):
        os.environ["PATH"] = FFMPEG_LOCATION + os.pathsep + os.environ.get("PATH", "")
else:
    import logging
    logging.getLogger("config").warning("FFmpeg không tìm thấy! Tính năng tải YouTube audio sẽ không hoạt động.")

# --- CDP (Chrome DevTools Protocol) Constants ---
CDP_DEBUG_PORT = AppConfig.get("cdp_debug_port", 9222)
CDP_CONNECT_TIMEOUT = float(AppConfig.get("cdp_connect_timeout", 5.0))
CDP_POLL_INTERVAL = float(AppConfig.get("cdp_poll_interval", 0.1))


class ConfigManager:
    """Quản lý file settings.json"""
    @staticmethod
    def load_settings():
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    @staticmethod
    def save_settings(settings):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Lỗi lưu settings: {e}")
            return False

class UiConfigManager:
    """Quản lý file ui_config.json cho Dev Mode"""
    
    _DEFAULT_UI_CONFIG = {
        "mixer": [
            {
                "id": "mix_music", "type": "slider", "label": "Nhạc", "icon": "♪", "color": "#14b8a6",
                "cc": "mix_music", "range": [0, 100], "default": 70, "unit": "", "has_mute": True, "has_inf_bottom": False, "hidden": False
            },
            {
                "id": "mix_mic", "type": "slider", "label": "Mic", "icon": "☉", "color": "#f97316",
                "cc": "mix_mic", "range": [-10, 10], "default": 0, "unit": "", "has_mute": True, "has_inf_bottom": True, "hidden": False
            },
            {
                "id": "mix_reverb", "type": "slider", "label": "Vang", "icon": "≡", "color": "#eab308",
                "cc": "mix_reverb", "range": [-10, 10], "default": 0, "unit": "", "has_mute": True, "has_inf_bottom": True, "hidden": False
            },
            {
                "id": "tone_music", "type": "slider", "label": "Giọng", "icon": "↕", "color": "#8b5cf6",
                "cc": "tone_music", "range": [-12, 12], "default": 0, "unit": "", "has_mute": False, "has_inf_bottom": False, "hidden": False
            }
        ],
        "tools": [
            {"id": "btn_fast_mode", "type": "button", "label": "Chế độ: Nhanh", "color": "#f97316", "action": "toggle_scan_mode", "desc": "Chuyển chế độ dò tone giữa Nhanh và Full", "hidden": False},
            {"id": "btn_rescan", "type": "button", "label": "Dò Lại", "color": "#14b8a6", "action": "force_rescan", "desc": "Buộc dò lại tone bài hát đang phát", "hidden": False},
            {"id": "btn_autotune", "type": "button", "label": "Auto-Tune", "color": "#ec4899", "action": "tone_auto", "desc": "Bật tắt Auto-Tune trên Studio One", "hidden": False},
            {"id": "btn_fixmeo", "type": "button", "label": "Fix Méo", "color": "#8b5cf6", "action": "fix_meo", "desc": "Bật tắt chế độ chống méo giọng", "hidden": False}
        ],
        "mode": [
            {"id": "mode_danca", "type": "button", "label": "Dân Ca", "color": "#ec4899", "action": "set_mode_danca", "hidden": False},
            {"id": "mode_lofi", "type": "button", "label": "Lofi", "color": "#14b8a6", "action": "set_mode_lofi", "hidden": False},
            {"id": "mode_remix", "type": "button", "label": "Remix", "color": "#f97316", "action": "set_mode_remix", "hidden": False},
            {"id": "mode_datheloai", "type": "button", "label": "Đa Thể Loại", "color": "#8b5cf6", "action": "set_mode_datheloai", "hidden": False}
        ]
    }

    @staticmethod
    def load_ui_config():
        if os.path.exists(UI_CONFIG_FILE):
            try:
                with open(UI_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    
    @staticmethod
    def save_ui_config(ui_config):
        try:
            with open(UI_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(ui_config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Lỗi lưu ui_config: {e}")
            return False
