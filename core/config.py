"""
Quang Lưu Studio — Configuration Management
Classes: AppConfig, ConfigManager
Constants: SETTINGS_FILE, SONGS_FILE, ACTIVATION_FILE, etc.
"""
import os
import sys
import json
import copy

from core.utils import find_ffmpeg

# --- CẤU HÌNH CỐT LÕI ---
SETTINGS_FILE = "settings.json"
SONGS_FILE = "saved_songs.json"
ACTIVATION_FILE = "activation.json"
MANUAL_TIMELINES_FILE = "manual_timelines.json"

# --- APP CONFIG (đọc từ file ngoài, không cần build lại exe) ---
APP_CONFIG_FILE = "app_config.json"

# Defaults nếu file không tồn tại hoặc thiếu field
_DEFAULT_APP_CONFIG = {
    "midi_port_name": "QuangLuuMIDI",
    "midi_cc": {
        "tone_music": 10, "tone_voice": 11,
        "mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "mix_backing": 23,
        "mode": 30, "autokey": 31, "score_trigger": 32,
        "key_root": 33, "key_scale": 34, "scale_type": 35,
        "tune_on_off": 36, "tone_auto": 31, "fix_meo": 36,
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
        """Tìm đường dẫn app_config.json — ưu tiên thư mục chứa exe"""
        if getattr(sys, 'frozen', False):
            # PyInstaller frozen: file nằm cạnh exe
            exe_dir = os.path.dirname(sys.executable)
        else:
            # Dev mode: file nằm cạnh source (project root, not core/)
            exe_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(exe_dir, APP_CONFIG_FILE)

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

                print(f"✅ App config loaded: {config_path}")
            except Exception as e:
                print(f"⚠️ Lỗi đọc {APP_CONFIG_FILE}: {e} — dùng giá trị mặc định")
        else:
            print(f"ℹ️ {APP_CONFIG_FILE} không tìm thấy — dùng giá trị mặc định")

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
    def reload(cls):
        """Force reload config từ file (VD: sau khi user sửa file)"""
        cls._data = None
        return cls.load()


# Load config ngay khi import module
AppConfig.load()
MIDI_PORT_NAME = AppConfig.get("midi_port_name", "QuangLuuMIDI")

# FFmpeg location (sử dụng consolidated find_ffmpeg từ core.utils)
FFMPEG_LOCATION = find_ffmpeg()
if FFMPEG_LOCATION:
    print(f"✅ FFmpeg found: {FFMPEG_LOCATION}")
    # Thêm vào PATH để yt-dlp download_ranges có thể tìm ffmpeg
    if FFMPEG_LOCATION not in os.environ.get("PATH", ""):
        os.environ["PATH"] = FFMPEG_LOCATION + os.pathsep + os.environ.get("PATH", "")
else:
    print("⚠️ FFmpeg không tìm thấy! Tính năng tải YouTube audio sẽ không hoạt động.")


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
