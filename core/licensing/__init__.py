"""
core.licensing — kích hoạt online + khoá theo máy, có offline grace.

Chỉ dùng stdlib (urllib) để không thêm dependency cho client.
ActivationManager (core/activation.py) tự động uỷ quyền sang đây khi
app_config.json có 'license_server_url'. Nếu không có → giữ luồng offline cũ.
"""
from core.licensing.client import (
    activate_online,
    server_configured,
    server_url,
    verify_online,
)
from core.licensing.device import get_fingerprint

__all__ = [
    "activate_online",
    "verify_online",
    "server_configured",
    "server_url",
    "get_fingerprint",
]
