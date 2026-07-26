"""
Quang Lưu Studio — Build capabilities (phát hiện năng lực lúc chạy).

Tách biệt với core.entitlements (license tier). Ở đây ta phát hiện những năng lực
phụ thuộc *build* — ví dụ bản "Heavy" có bundle QtWebEngine (để dùng màn hình
karaoke nhúng) còn bản "Light" thì không (giảm ~250MB cho máy yếu).

Cùng một codebase chạy được cả 2 build: code gọi embedded_player_available() để
bật/tắt UI player nhúng. Bản Light → False → mọi thứ liên quan player nhúng ẩn đi
và app hoạt động y như cũ (mở trình duyệt ngoài).
"""

# ===== Phát hiện QtWebEngine (cho màn hình karaoke nhúng) =====
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    _WEBENGINE_AVAILABLE = True
except ImportError:
    _WEBENGINE_AVAILABLE = False


def embedded_player_available() -> bool:
    """True nếu build hiện tại có QtWebEngine → dùng được màn hình karaoke nhúng."""
    return _WEBENGINE_AVAILABLE
