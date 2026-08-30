"""
Quang Lưu Studio — Lớp entitlement (phân tầng tính năng Standard / Premium).

Nguồn chân lý DUY NHẤT cho UI/engine khi quyết định mở/khóa tính năng Premium.
Mọi nơi cần kiểm tra quyền nên import module này, KHÔNG tự đọc activation.json.

Quy ước tier:
  - "standard": mặc định — chưa kích hoạt, đang dùng thử, hoặc license gói standard.
  - "premium" : chỉ khi license token còn hiệu lực và claim `plan` là premium.

Tier nằm trong claim của token đã ký RS256, nên sửa tay activation.json chỉ làm
hỏng chữ ký → tụt về standard, không lên được premium.

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
    "auto_echo",     # Tự động bật/tắt Vang theo nhạc
    "auto_noise",    # Tự động tắt Khử ồn khi có nhạc, bật lại khi hết nhạc
})


def current_plan() -> str:
    """Trả tier hiện tại: "standard" | "premium" (theo claim đã xác minh chữ ký)."""
    try:
        from core.licensing import client
        return client.current_plan()
    except Exception as e:  # pragma: no cover - phòng thủ
        log.debug("current_plan fallback standard: %s", e)
        return "standard"


def is_premium() -> bool:
    """
    True khi: license gói premium VÀ còn hiệu lực (đã kích hoạt, chưa hết hạn,
    chưa lapse grace). Trial → False.
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
