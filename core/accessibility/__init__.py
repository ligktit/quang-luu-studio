"""
Quang Lưu Studio — Accessibility package.

Cung cấp các module trợ năng cho người khiếm thị / thị lực kém:
- speaker:     TTS engine (pyttsx3 / SAPI5).
- announcer:   Cầu nối state changes → Speaker.
- shortcuts:   Đăng ký bộ QShortcut tập trung.
- theme:       High-contrast palette + font scale.
- voice_input: Voice command (Vosk offline, push-to-talk).

Mỗi module đều "fail-soft": nếu thư viện ngoài chưa cài đặt thì module
trả về stub no-op và log cảnh báo, app vẫn chạy bình thường.
"""

from .speaker import Speaker, get_speaker
from .announcer import Announcer
from .theme import ThemeManager
from .shortcuts import register_shortcuts

__all__ = [
    "Speaker",
    "get_speaker",
    "Announcer",
    "ThemeManager",
    "register_shortcuts",
]
