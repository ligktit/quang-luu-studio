"""
Quang Lưu Studio — Build capabilities (phát hiện năng lực lúc chạy).

Tách biệt với core.entitlements (license tier). Ở đây ta phát hiện những năng lực
phụ thuộc *build* — ví dụ bản "Heavy" có bundle QtWebEngine (để dùng màn hình
karaoke nhúng) còn bản "Light" thì không (giảm ~250MB cho máy yếu).

Cùng một codebase chạy được cả 2 build: code gọi embedded_player_available() để
bật/tắt UI player nhúng. Bản Light → False → mọi thứ liên quan player nhúng ẩn đi
và app hoạt động y như cũ (mở trình duyệt ngoài).

Vì sao phải giữ LÝ DO chứ không chỉ True/False: kết quả False có hai nghĩa hoàn
toàn khác nhau —

  1. Đúng là bản Light  → không có gì phải sửa, chỉ cần nói với khách "cài bản
     đầy đủ".
  2. Bản Heavy mà nạp QtWebEngine hỏng (file bị phần mềm diệt virus cách ly,
     thiếu DLL, cài đè lên bản cũ...) → là LỖI, và tệ hơn: `core/updater/
     _version_check.py` dùng chính hàm này để chọn file cài lúc tự cập nhật, nên
     một lần nhận nhầm là khách bị đẩy sang bản Light vĩnh viễn.

Nhìn vào True/False thì hai ca này giống hệt nhau. Có thông điệp lỗi thì phân
biệt được ngay từ log của khách.
"""

# ===== Phát hiện QtWebEngine (cho màn hình karaoke nhúng) =====
# Bắt Exception chứ không chỉ ImportError: trên máy khách, QtWebEngine hỏng có
# thể ném OSError (DLL bị chặn), RuntimeError (xung đột phiên bản Qt)... Để lọt
# một loại ngoại lệ nào đó ra ngoài là dựng cả dialog Thiết lập.
_WEBENGINE_ERROR = None
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    _WEBENGINE_AVAILABLE = True
except Exception as _exc:      # noqa: BLE001 - cố ý bắt rộng, xem chú thích trên
    _WEBENGINE_AVAILABLE = False
    _WEBENGINE_ERROR = f"{type(_exc).__name__}: {_exc}"


def embedded_player_available() -> bool:
    """True nếu build hiện tại có QtWebEngine → dùng được màn hình karaoke nhúng."""
    return _WEBENGINE_AVAILABLE


def embedded_player_error() -> str:
    """Thông điệp lỗi lúc nạp QtWebEngine, hoặc "" nếu nạp được.

    Chuỗi rỗng khi `embedded_player_available()` là True. Khi False, chuỗi này
    phân biệt bản Light thật sự với bản Heavy bị hỏng — xem docstring của module.
    """
    return _WEBENGINE_ERROR or ""


def build_variant() -> str:
    """"Heavy" hoặc "Light" — theo đúng cách bộ cài đặt tên."""
    return "Heavy" if _WEBENGINE_AVAILABLE else "Light"


def describe() -> str:
    """Một dòng cho log/chẩn đoán."""
    if _WEBENGINE_AVAILABLE:
        return "Ban Heavy - co QtWebEngine, dung duoc man hinh karaoke nhung"
    if _WEBENGINE_ERROR and "No module named" in _WEBENGINE_ERROR:
        return "Ban Light - khong kem QtWebEngine (dung theo thiet ke)"
    return (f"Ban Heavy NHUNG nap QtWebEngine that bai: {_WEBENGINE_ERROR}"
            if _WEBENGINE_ERROR else "Khong xac dinh duoc bien the build")
