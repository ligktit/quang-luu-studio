"""Header panel builder for MainDashboard."""
from PySide6.QtWidgets import QComboBox, QLabel, QSizePolicy
from PySide6.QtCore import Qt

from ui.design_tokens import C, SP, FONT
from ui.components.painter_button import PainterButton
from ui.components.painter_header import PaintedHeaderBar, PaintedMidiDot
from ui.components.marquee import SmoothMarqueeLabel
from ui.components.svg_icons import SVG_EYE_OPEN, SVG_HELP, SVG_SETTINGS
from ui.components.tone_display import ToneDisplay, ScaleToggle, NextTonePill


def build_header(dashboard) -> PaintedHeaderBar:
    header = PaintedHeaderBar(height=55)
    header.setAccessibleName("Thanh tiêu đề Quang Lưu Studio")
    layout = header.layout()

    # Tag PREMIUM (texture kim cương) — chỉ hiện cho gói Premium.
    dashboard._premium_tag = None
    try:
        from core import entitlements
        if entitlements.is_premium():
            from ui.components.premium_tag import PremiumTag
            dashboard._premium_tag = PremiumTag("PREMIUM")
            dashboard._premium_tag.setToolTip("Tài khoản Premium")
            dashboard._premium_tag.setAccessibleName("Huy hiệu Premium")
            layout.addWidget(dashboard._premium_tag)
            layout.addSpacing(SP.SM)
    except Exception as e:
        print(f"[PREMIUM-TAG] init lỗi: {e}")

    dashboard._midi_dot = PaintedMidiDot()
    dashboard._midi_dot.setToolTip("Kết nối MIDI với Studio One")
    dashboard._midi_dot.setAccessibleName("Đèn báo MIDI")
    dashboard._midi_dot.setAccessibleDescription("Xanh: đã kết nối. Đỏ: mất kết nối.")
    layout.addWidget(dashboard._midi_dot)
    layout.addSpacing(4)

    dashboard._browser_dot = PaintedMidiDot()
    dashboard._browser_dot.setToolTip("Đồng bộ với trình duyệt")
    dashboard._browser_dot.setAccessibleName("Đèn báo trình duyệt")
    dashboard._browser_dot.setAccessibleDescription(
        "Xanh: tốt. Vàng: chế độ dự phòng. Đỏ: chưa kết nối."
    )
    layout.addWidget(dashboard._browser_dot)
    layout.addSpacing(SP.XS)

    dashboard._marquee_widget = SmoothMarqueeLabel(dashboard._marquee_text_value, color="#fc8403")
    dashboard._marquee_widget.setFixedHeight(30)
    dashboard._marquee_widget.setAccessibleName("Bảng thông báo")
    dashboard._marquee_widget.setAccessibleDescription("Hiển thị tên bài hát và thông tin tone đang phát")
    # VIP/Premium: viền LED chạy quanh marquee.
    try:
        from core import entitlements
        if entitlements.is_premium():
            dashboard._marquee_widget.setFixedHeight(40)
            dashboard._marquee_widget.set_led_border(True)
    except Exception as e:
        print(f"[PREMIUM-LED] init lỗi: {e}")
    layout.addWidget(dashboard._marquee_widget, 1)
    dashboard.marquee_label = dashboard._marquee_widget

    layout.addStretch()

    dashboard.autokey_dot = PaintedMidiDot()
    dashboard.autokey_dot.setAccessibleName("Đèn báo dò tone")
    dashboard.autokey_dot.setAccessibleDescription("Xanh: đã dò ra tone. Xám: đang chờ.")
    layout.addWidget(dashboard.autokey_dot)
    layout.addSpacing(SP.XS)

    # Ô tone — vẫn là QComboBox tạo dáng bằng QSS như trước, chỉ tăng cỡ chữ
    # (13 → 18px) để nhìn được từ xa. Mọi chỗ gọi cũ giữ nguyên.
    dashboard.tone_combo = ToneDisplay()
    _NOTE_VI = ["Đô", "Đô thăng", "Rê", "Rê thăng", "Mi", "Fa",
                "Fa thăng", "Sol", "Sol thăng", "La", "La thăng", "Si"]
    _NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    dashboard.tone_combo.addItems(_NOTES)
    for _i, _vi in enumerate(_NOTE_VI):
        dashboard.tone_combo.setItemData(_i, f"{_NOTES[_i]} — {_vi}", Qt.ToolTipRole)
    dashboard.tone_combo.setAccessibleName("Chọn tone")
    dashboard.tone_combo.setAccessibleDescription("Chọn nốt gốc của bài hát, từ Đô (C) đến Si (B)")
    dashboard.tone_combo.currentTextChanged.connect(dashboard._on_tone_selected)
    layout.addWidget(dashboard.tone_combo)
    layout.addSpacing(SP.XS)

    # Major/Minor: NÚT một chạm (PainterButton, cùng khuôn với các nút khác trên
    # header) thay cho danh sách xổ xuống.
    dashboard.scale_combo = ScaleToggle()
    dashboard.scale_combo.setAccessibleName("Đổi thể Major Minor")
    dashboard.scale_combo.currentTextChanged.connect(dashboard._on_scale_selected)
    layout.addWidget(dashboard.scale_combo)

    # Nút "Tương đối" — đổi C Major ↔ A Minor một chạm (đổi cả nốt gốc lẫn thể)
    layout.addSpacing(SP.XS)
    dashboard._relative_btn = PainterButton(
        "↔", color=C["light_purple"], height=28, radius=6,
        font_size=14, fixed_width=30,
    )
    dashboard._relative_btn.setToolTip(
        "Đổi tone tương đối (C Major ↔ A Minor)"
    )
    dashboard._relative_btn.setAccessibleName("Đổi tone tương đối")
    dashboard._relative_btn.setCursor(Qt.PointingHandCursor)
    dashboard._relative_btn.clicked.connect(dashboard._on_toggle_relative)
    layout.addWidget(dashboard._relative_btn)

    # Ô "kế tiếp" — chỉ hiện khi bài có timeline nhiều đoạn (xem
    # MainDashboard._tone_ticker_sync). Ẩn mặc định để header không bị rối.
    layout.addSpacing(SP.XS)
    dashboard._next_tone_pill = NextTonePill()
    dashboard._next_tone_pill.setVisible(False)
    layout.addWidget(dashboard._next_tone_pill)

    layout.addSpacing(SP.SM)
    # Hỗ trợ — kênh hai chiều với đội kỹ thuật. Nút đỏ lên khi có trả lời chưa
    # đọc (MainDashboard._refresh_support_badge). Ẩn khi khoá kiosk: khách hát
    # không phải người gửi ticket.
    dashboard._support_btn = PainterButton(
        "", color=C["card_hover"], height=28, radius=6,
        font_size=10, svg_content=SVG_HELP, svg_size=16, fixed_width=30,
    )
    dashboard._support_btn.setToolTip("Hỗ trợ kỹ thuật")
    dashboard._support_btn.setAccessibleName("Mở hộp thoại hỗ trợ")
    dashboard._support_btn.setAccessibleDescription("Gửi yêu cầu và xem trả lời ngay trong app")
    dashboard._support_btn.setCursor(Qt.PointingHandCursor)
    dashboard._support_btn.clicked.connect(dashboard._show_support_dialog)
    layout.addWidget(dashboard._support_btn)

    layout.addSpacing(SP.XS)
    dashboard._settings_btn = PainterButton(
        "", color=C["card_hover"], height=28, radius=6,
        font_size=10, svg_content=SVG_SETTINGS, svg_size=16, fixed_width=30,
    )
    dashboard._settings_btn.setToolTip("Cài đặt · Ctrl+,")
    dashboard._settings_btn.setAccessibleName("Mở thiết lập")
    dashboard._settings_btn.setCursor(Qt.PointingHandCursor)
    dashboard._settings_btn.clicked.connect(dashboard._show_settings_dialog)
    layout.addWidget(dashboard._settings_btn)

    # Nút mắt ẩn/hiện Studio One. Ở chế độ khách nút bị setVisible(False) — widget
    # ẩn thì không vẽ, không bấm được, không nằm trong thứ tự Tab và trình đọc màn
    # hình cũng bỏ qua, tức là khách không còn lối nào chạm tới Studio One.
    # Bật/tắt qua MainDashboard._apply_kiosk_visibility().
    dashboard._studio_one_visible = True
    dashboard._eye_btn = PainterButton(
        "", color=C["card_hover"], height=28, radius=6,
        font_size=10, svg_content=SVG_EYE_OPEN, svg_size=16, fixed_width=30,
    )
    dashboard._eye_btn.setToolTip("Ẩn/Hiện Studio One + Plugin")
    dashboard._eye_btn.setAccessibleName("Ẩn hiện Studio One")
    dashboard._eye_btn.setCursor(Qt.PointingHandCursor)
    dashboard._eye_btn.clicked.connect(dashboard._on_eye_toggle_studio_one)
    layout.addWidget(dashboard._eye_btn)

    # Huy hiệu nhắc kỹ thuật viên rằng máy đang mở khoá (kẻo quên khoá lại).
    dashboard._tech_badge = QLabel("KỸ THUẬT")
    dashboard._tech_badge.setStyleSheet(
        f"color: {C['bg']}; background-color: {C['orange']};"
        f" border-radius: 6px; padding: 3px 8px; font-size: 10px;"
        f" font-weight: 900; font-family: {FONT};"
    )
    dashboard._tech_badge.setToolTip("Đang mở khoá · Ctrl+Alt+Shift+T để khoá")
    dashboard._tech_badge.setAccessibleName("Đang mở khoá kỹ thuật")
    dashboard._tech_badge.setVisible(False)
    layout.addSpacing(SP.XS)
    layout.addWidget(dashboard._tech_badge)

    return header
