"""
Quang Lưu Studio — Lớp entitlement (phân tầng tính năng Standard / Premium).

Nguồn chân lý DUY NHẤT cho UI/engine khi quyết định mở/khóa tính năng Premium.
Mọi nơi cần kiểm tra quyền nên import module này, KHÔNG tự đọc activation.json.

Quy ước tier:
  - "standard": mặc định (mọi mã offline, trial, và mã online gói standard).
  - "premium" : chỉ khi có license online gói premium còn hiệu lực.

Trial 3 ngày = Standard (theo quyết định sản phẩm) → is_premium() luôn False
khi đang trial.
"""
import logging

log = logging.getLogger(__name__)

# Tên các tính năng bị khóa ở Premium. Dùng làm khóa tra cứu trong UI/engine.
PREMIUM_FEATURES = frozenset({
    "scoring",       # Chấm điểm
    "smart_recall",  # Preset tone/mix/mode theo bài
    "cloud_sync",    # Đồng bộ thư viện
    "progress",      # Bảng tiến bộ luyện hát
    "setlist",       # Live Setlist / Auto-Pilot
})


def current_plan() -> str:
    """
    Trả tier hiện tại: "standard" | "premium".

    Offline mode (server license chưa cấu hình) hoặc bất kỳ lỗi nào → "standard"
    (fail-safe: không vô tình mở Premium).
    """
    try:
        from core.licensing import client
        if client.server_configured() and client.has_online_license():
            return client.current_plan()
    except Exception as e:  # pragma: no cover - phòng thủ
        log.debug("current_plan fallback standard: %s", e)
    return "standard"


def is_premium() -> bool:
    """
    True khi: có license online gói premium VÀ license còn hiệu lực
    (đã kích hoạt, chưa hết hạn/grace). Trial → False.
    """
    try:
        if current_plan() != "premium":
            return False
        from core.activation import ActivationManager
        # Trial không tính là activated → loại trừ tự nhiên.
        return ActivationManager.is_activated() and not ActivationManager.is_expired()
    except Exception as e:  # pragma: no cover
        log.debug("is_premium fallback False: %s", e)
        return False


def has_feature(name: str) -> bool:
    """
    Tính năng `name` có được phép dùng không.
    Tính năng không nằm trong PREMIUM_FEATURES → luôn cho phép (Standard).
    """
    if name not in PREMIUM_FEATURES:
        return True
    return is_premium()
