"""Header panel builder for MainDashboard."""
from PySide6.QtWidgets import QComboBox, QSizePolicy
from PySide6.QtCore import Qt

from ui.design_tokens import C, SP, FONT
from ui.components.painter_button import PainterButton
from ui.components.painter_header import PaintedHeaderBar, PaintedMidiDot
from ui.components.marquee import SmoothMarqueeLabel
from ui.components.svg_icons import SVG_EYE_OPEN, SVG_SETTINGS


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
    dashboard._midi_dot.setToolTip("Trạng thái kết nối MIDI (Studio One/Loopback)")
    dashboard._midi_dot.setAccessibleName("Đèn báo MIDI")
    dashboard._midi_dot.setAccessibleDescription(
        "Hiển thị trạng thái kết nối MIDI với Studio One. Xanh là đã kết nối, đỏ là mất kết nối."
    )
    layout.addWidget(dashboard._midi_dot)
    layout.addSpacing(4)

    dashboard._browser_dot = PaintedMidiDot()
    dashboard._browser_dot.setToolTip("Trạng thái đồng bộ trình duyệt (CDP/WinRT)")
    dashboard._browser_dot.setAccessibleName("Đèn báo trình duyệt")
    dashboard._browser_dot.setAccessibleDescription(
        "Hiển thị trạng thái đồng bộ với trình duyệt. Xanh lá là CDP đã kết nối, vàng là WinRT, đỏ là chưa kết nối."
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
    dashboard.autokey_dot.setAccessibleDescription("Xanh lá là đã phát hiện tone, xám là đang chờ")
    layout.addWidget(dashboard.autokey_dot)
    layout.addSpacing(SP.XS)

    dashboard.tone_combo = QComboBox()
    _NOTE_VI = ["Đô", "Đô thăng", "Rê", "Rê thăng", "Mi", "Fa",
                "Fa thăng", "Sol", "Sol thăng", "La", "La thăng", "Si"]
    _NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    dashboard.tone_combo.addItems(_NOTES)
    for _i, _vi in enumerate(_NOTE_VI):
        dashboard.tone_combo.setItemData(_i, f"{_NOTES[_i]} — {_vi}", Qt.ToolTipRole)
    dashboard.tone_combo.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    dashboard.tone_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    dashboard.tone_combo.setAccessibleName("Chọn tone")
    dashboard.tone_combo.setAccessibleDescription("Chọn nốt gốc của bài hát, từ Đô (C) đến Si (B)")
    dashboard.tone_combo.currentTextChanged.connect(dashboard._on_tone_selected)
    layout.addWidget(dashboard.tone_combo)
    layout.addSpacing(SP.XS)

    dashboard.scale_combo = QComboBox()
    dashboard.scale_combo.addItems(["Major", "Minor"])
    dashboard.scale_combo.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    dashboard.scale_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
    dashboard.scale_combo.setAccessibleName("Chọn thể")
    dashboard.scale_combo.setAccessibleDescription("Chọn trưởng (Major) hoặc thứ (Minor)")
    dashboard.scale_combo.setItemData(0, "Trưởng (Major)", Qt.ToolTipRole)
    dashboard.scale_combo.setItemData(1, "Thứ (Minor)", Qt.ToolTipRole)
    dashboard.scale_combo.currentTextChanged.connect(dashboard._on_scale_selected)
    layout.addWidget(dashboard.scale_combo)

    # Nút "Tương đối" — đổi C Major ↔ A Minor một chạm (đổi cả nốt gốc lẫn thể)
    layout.addSpacing(SP.XS)
    dashboard._relative_btn = PainterButton(
        "↔", color=C["light_purple"], height=28, radius=6,
        font_size=14, fixed_width=30,
    )
    dashboard._relative_btn.setToolTip(
        "Đổi sang tone tương đối (vd C Trưởng ↔ La Thứ).\n"
        "Dùng khi bài là La Thứ nhưng app hiện Đô Trưởng."
    )
    dashboard._relative_btn.setAccessibleName("Đổi tone tương đối")
    dashboard._relative_btn.setAccessibleDescription(
        "Chuyển nhanh giữa tone trưởng và tone thứ tương đối, ví dụ Đô Trưởng đổi thành La Thứ"
    )
    dashboard._relative_btn.setCursor(Qt.PointingHandCursor)
    dashboard._relative_btn.clicked.connect(dashboard._on_toggle_relative)
    layout.addWidget(dashboard._relative_btn)

    layout.addSpacing(SP.SM)
    dashboard._settings_btn = PainterButton(
        "", color=C["card_hover"], height=28, radius=6,
        font_size=10, svg_content=SVG_SETTINGS, svg_size=16, fixed_width=30,
    )
    dashboard._settings_btn.setToolTip("Cài đặt")
    dashboard._settings_btn.setAccessibleName("Mở thiết lập")
    dashboard._settings_btn.setAccessibleDescription("Mở hộp thoại thiết lập hệ thống. Phím tắt Ctrl+Phẩy")
    dashboard._settings_btn.setCursor(Qt.PointingHandCursor)
    dashboard._settings_btn.clicked.connect(dashboard._show_settings_dialog)
    layout.addWidget(dashboard._settings_btn)

    dashboard._studio_one_visible = True
    dashboard._eye_btn = PainterButton(
        "", color=C["card_hover"], height=28, radius=6,
        font_size=10, svg_content=SVG_EYE_OPEN, svg_size=16, fixed_width=30,
    )
    dashboard._eye_btn.setToolTip("Ẩn/Hiện Studio One + Plugin")
    dashboard._eye_btn.setAccessibleName("Ẩn hiện Studio One")
    dashboard._eye_btn.setAccessibleDescription("Ẩn hoặc hiện cửa sổ Studio One và các plugin đi kèm")
    dashboard._eye_btn.setCursor(Qt.PointingHandCursor)
    dashboard._eye_btn.clicked.connect(dashboard._on_eye_toggle_studio_one)
    layout.addWidget(dashboard._eye_btn)

    return header
