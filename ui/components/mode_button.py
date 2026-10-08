"""
ui.components.mode_button
=========================
Nút MODE (Dân Ca, Lofi, Remix, Đa Thể Loại và mode tự thêm ở Dev Mode).

Vì sao có nó: PainterButton luôn tô đầy màu dù bật hay tắt, "đang bật" chỉ là
một chấm trắng 4px ở góc — đang hát, liếc từ xa không biết mode nào đang chạy.
Nút này đổi hẳn ngôn ngữ hình ảnh của trạng thái:

  TẮT  → "ghost": nền tối trong suốt, viền mảnh màu mode, chữ màu mode.
  BẬT  → đổ đầy gradient màu mode, viền neon sáng, quầng sáng mềm bao quanh,
         chấm LED trắng trước chữ, chữ trắng đậm.

Chỉ phần vẽ khác PainterButton; hover, nhấn, click, lấp lánh theo nhạc
(Premium) và menu chuột phải Dev Mode dùng nguyên của lớp cha. Nút TOOLS
không dùng lớp này.
"""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QLinearGradient, QRadialGradient

from ui.design_tokens import C
from ui.components.painter_button import PainterButton

# Thân nút lùi vào trong widget để quầng sáng của trạng thái BẬT có chỗ mà
# không làm hàng nút cao thêm nhiều.
_INSET = 2.0
_LED_R = 2.5        # bán kính chấm LED
_LED_GAP = 5        # khoảng cách LED → chữ


class ModeToggleButton(PainterButton):
    """PainterButton vẽ lại theo trạng thái: tắt = viền mỏng, bật = sáng."""

    def __init__(self, text="", color="#38BDF8", height=28, radius=8, font_size=9,
                 parent=None):
        super().__init__(text, color=color, height=height, radius=radius,
                         font_size=font_size, parent=parent)
        self._apply_state_description()

    # ── trạng thái ──────────────────────────────────────────────────────────
    def setActive(self, a):
        super().setActive(bool(a))
        self._apply_state_description()

    def isActive(self) -> bool:
        return bool(self._active)

    def _apply_state_description(self):
        # Phần đọc màn hình (TTS) đọc được trạng thái, không chỉ nhìn.
        self.setAccessibleDescription("Đang bật" if self._active else "Đang tắt")

    # ── vẽ ──────────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = self._radius
        body = QRectF(_INSET, _INSET, w - 2 * _INSET, h - 2 * _INSET)

        base = QColor(self._color)
        if not self._enabled:
            base = QColor(C["card_hover"])

        if self._active:
            self._paint_on(p, body, base, w, h, r)
        else:
            self._paint_off(p, body, base, r)

        if self._music_reactive and self._pulse_glow > 0.03 and self._enabled:
            self._paint_music_glow(p, w, h, r)
        p.end()

    def _paint_off(self, p, body, base, r):
        """Ghost: nền tối, viền mảnh màu mode, chữ màu mode."""
        fill = QColor(0, 0, 0, 55)
        if self._pressed and self._enabled:
            fill = QColor(base); fill.setAlpha(70)
        elif self._hover and self._enabled:
            fill = QColor(base); fill.setAlpha(34)

        border = QColor(base)
        border.setAlpha(190 if (self._hover and self._enabled) else 140)
        p.setPen(QPen(border, 1))
        p.setBrush(fill)
        p.drawRoundedRect(body, r, r)

        text_color = self._lighten(base, 0.30) if self._enabled else QColor(C["text_muted"])
        self._draw_label(p, body, text_color, led=False)

    def _paint_on(self, p, body, base, w, h, r):
        """Đổ đầy màu mode + viền neon + quầng sáng + LED."""
        # Quầng sáng mềm bao ngoài thân nút.
        halo = QColor(base); halo.setAlpha(70)
        p.setPen(QPen(halo, 3))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r + 1, r + 1)

        grad = QLinearGradient(0, body.top(), 0, body.bottom())
        if self._pressed and self._enabled:
            grad.setColorAt(0.0, self._darken(base, 0.15))
            grad.setColorAt(1.0, base)
        elif self._hover and self._enabled:
            grad.setColorAt(0.0, self._lighten(base, 0.25))
            grad.setColorAt(0.5, self._lighten(base, 0.08))
            grad.setColorAt(1.0, base)
        else:
            grad.setColorAt(0.0, self._lighten(base, 0.14))
            grad.setColorAt(0.5, base)
            grad.setColorAt(1.0, self._darken(base, 0.10))

        ring = self._lighten(base, 0.45); ring.setAlpha(230)
        p.setPen(QPen(ring, 1.5))
        p.setBrush(grad)
        p.drawRoundedRect(body, r, r)

        # Vệt sáng trên (3D) như PainterButton.
        if not self._pressed:
            hi = QLinearGradient(0, body.top(), 0, body.top() + body.height() * 0.45)
            hi.setColorAt(0, QColor(255, 255, 255, 48))
            hi.setColorAt(1, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(hi)
            p.drawRoundedRect(body.adjusted(1, 1, -1, -body.height() * 0.5), r - 1, r - 1)

        self._draw_label(p, body, QColor("#FFFFFF"), led=True)

    def _draw_label(self, p, body, text_color, led):
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPixelSize(self._font_size)
        font.setBold(True)
        p.setFont(font)
        fm = p.fontMetrics()
        text_w = fm.horizontalAdvance(self._text)

        led_span = (_LED_R * 2 + _LED_GAP) if led else 0
        total = text_w + led_span
        x0 = body.left() + (body.width() - total) / 2
        if self._pressed and self._enabled:
            x0 += 1
        cy = body.center().y()

        if led:
            lx, ly = x0 + _LED_R, cy
            glow = QRadialGradient(lx, ly, _LED_R * 3)
            glow.setColorAt(0.0, QColor(255, 255, 255, 170))
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QRectF(lx - _LED_R * 3, ly - _LED_R * 3, _LED_R * 6, _LED_R * 6))
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QRectF(lx - _LED_R, ly - _LED_R, _LED_R * 2, _LED_R * 2))

        text_rect = QRectF(x0 + led_span, body.top(), text_w + 2, body.height())
        if led:
            p.setPen(QColor(0, 0, 0, 70))
            p.drawText(text_rect.translated(1, 1), Qt.AlignVCenter | Qt.AlignLeft, self._text)
        p.setPen(text_color)
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self._text)
