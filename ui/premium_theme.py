"""
ui.premium_theme
================
Theme "Gold & Kim cương" (Diamond) dành cho khách VIP/Premium.

Toàn app đọc màu từ dict `C` và `PAINTER` trong ui.design_tokens, còn QSS toàn
cục (`APP_QSS = load_qss()`) đóng băng lúc import frontend_qt. Vì vậy hàm
`apply_if_premium()` PHẢI được gọi **trước khi import frontend_qt** (xem main.py)
để ghi đè palette in-place — mọi widget dựng sau đó sẽ mang tông vàng/kim cương.

- Standard: không áp → giữ tông Navy gốc.
- Premium: nền đen-vàng sang trọng, accent chính VÀNG GOLD, accent phụ KIM CƯƠNG
  (xanh băng icy-blue). Đỏ/xanh lá giữ nguyên ngữ nghĩa (nguy hiểm/thành công).

Idempotent: chỉ áp 1 lần.
"""
from __future__ import annotations

_applied = False

# ── Bảng màu Gold & Diamond ───────────────────────────────────────────────────
# Nền cửa sổ: gradient chéo VÀNG GOLD (góc trên-trái) → đen ấm (giữa) → KIM CƯƠNG
# xanh băng (góc dưới-phải). Đủ tối ở giữa để nội dung vẫn tương phản tốt.
_WINDOW_BG_GRADIENT = (
    "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
    "stop:0 #3A2C12, stop:0.30 #1B1408, stop:0.55 #15110B, "
    "stop:0.80 #122029, stop:1 #1A3038)"
)

_C_GOLD = {
    # Nền nâu-vàng tối ấm (sáng hơn để thấy rõ tông vàng)
    "bg":           "#171008",
    "card":         "#241B0D",
    "card_hover":   "#352A18",

    # Accent chính = VÀNG GOLD; phụ = KIM CƯƠNG (xanh băng)
    "primary":      "#E9C45A",   # gold
    "teal":         "#E9C45A",   # alias primary → gold
    "creative":     "#86D9F2",   # diamond icy-blue
    "light_purple": "#86D9F2",   # alias creative → diamond
    "deep_purple":  "#4FA3C7",   # diamond đậm
    "blue":         "#7FC9EE",   # diamond
    "orange":       "#F4B53A",   # amber gold
    "pink":         "#E7B58C",   # champagne / rose-gold

    # Ngữ nghĩa giữ nguyên
    "accent":       "#EF4444",   # đỏ nguy hiểm
    "green":        "#10B981",   # xanh thành công

    # Chữ ấm (ngà)
    "text":         "#FBF6E9",
    "text_muted":   "#BCAE92",

    # Viền vàng tối
    "border":       "#4A3E22",
}

_PAINTER_GOLD = {
    # Fader track
    "track_bg":        "#221d10",
    "track_groove_l":  "#322a18",
    "track_groove_m":  "#43381f",
    "track_tick":      "#5a4d2c",
    # Fader handle — kim loại VÀNG
    "handle_top":      "#F5DE92",
    "handle_mid":      "#CBA64A",
    "handle_bot":      "#8A6E26",
    "handle_border":   "#FBEAB0",
    "handle_grip":     "#FFF4C8",
    "handle_grip_sub": "#a08a52",
    # Knob vàng
    "knob_outer":      "#3a3018",
    "knob_inner_top":  "#E8CF86",
    "knob_inner_bot":  "#9A7E36",
    "knob_pointer":    "#FFF3C8",
    "arc_bg":          "#221d10",
    # Glass panel — kính vàng
    "glass_bg":        "rgba(34, 28, 14, 180)",
    "glass_border":    "rgba(200, 170, 90, 70)",
    "glass_highlight": "rgba(255, 240, 200, 16)",
    # Glow
    "glow_blue":       "#E9C45A",   # (giữ tên) → gold
    "glow_orange":     "#F4B53A",
    # Header
    "header_top":      "#16120a",
    "header_bot":      "#0d0a05",
    "header_line":     "rgba(233, 196, 90, 50)",
    # Waveform hero — gold → champagne → diamond
    "waveform_bg":     "rgba(14, 11, 5, 200)",
    "waveform_grad_1": "#F4CC55",   # gold
    "waveform_grad_2": "#FBE6A8",   # champagne nhạt
    "waveform_grad_3": "#9FE0FF",   # diamond
    "waveform_grid":   "rgba(233, 196, 90, 14)",
    "waveform_reflect":"rgba(233, 196, 90, 28)",
    # Tab dock
    "tab_active":      "#E9C45A",
    "tab_inactive":    "#8a7c54",
    "tab_bar_bg":      "rgba(18, 14, 7, 240)",
    "tab_indicator":   "#E9C45A",
    # Transport
    "transport_bg":    "rgba(20, 16, 8, 200)",
    "transport_btn":   "rgba(160, 140, 80, 120)",
}


def apply_gold_diamond() -> None:
    """Ghi đè palette in-place sang tông Gold & Diamond (không kiểm tra gói)."""
    global _applied
    if _applied:
        return
    import ui.design_tokens as dt
    dt.C.update(_C_GOLD)
    dt.PAINTER.update(_PAINTER_GOLD)
    # Nền cửa sổ chính → gradient vàng/kim cương (load_qss đọc WINDOW_BG).
    dt.WINDOW_BG = _WINDOW_BG_GRADIENT
    # Đồng bộ dải visualizer Premium sang gold/diamond cho ăn nhập.
    try:
        from ui.components import premium_visualizer as _pv
        _pv._C1 = (244, 204, 85)    # gold
        _pv._C2 = (251, 230, 168)   # champagne
        _pv._C3 = (159, 224, 255)   # diamond
    except Exception:
        pass
    _applied = True


def apply_if_premium() -> bool:
    """Áp theme nếu tài khoản là Premium. Trả True nếu đã áp. Fail-soft."""
    try:
        from core import entitlements
        if not entitlements.is_premium():
            return False
        apply_gold_diamond()
        return True
    except Exception as e:
        print(f"[PREMIUM-THEME] apply lỗi: {e}")
        return False
