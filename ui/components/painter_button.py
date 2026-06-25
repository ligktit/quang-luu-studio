"""
ui.components.painter_button
==============================
Custom QPainter button — gradient body + neon glow hover.

Features:
  - 3D beveled gradient background
  - Neon glow border on hover (color-matched)
  - Pressed state: darker gradient + inset feel
  - Disabled state: desaturated
  - Smooth state transitions
"""
import math
import random

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, Signal, QRectF, QSize, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QFontMetrics,
    QLinearGradient, QRadialGradient, QPainterPath
)
from ui.design_tokens import C, FONT, PAINTER


class PainterButton(QWidget):
    """
    Custom-painted button with gradient, glow, and smooth visuals.
    Emits clicked() signal.
    """
    clicked = Signal()

    def __init__(self, text="", color="#38BDF8", height=30,
                 radius=8, font_size=11, svg_content=None, svg_size=18, fixed_width=None, parent=None):
        super().__init__(parent)
        self._text = text
        self._color = QColor(color)
        self._height = height
        self._radius = radius
        self._font_size = font_size
        self._hover = False
        self._pressed = False
        self._enabled = True
        self._active = False  # for toggle states
        self._svg_content = svg_content
        self._svg_size = svg_size
        self._svg_renderer = None

        # Lấp lánh theo nhạc (Premium) — tắt mặc định, bật qua set_music_reactive().
        self._music_reactive = False
        self._pulse_glow = 0.0      # 0..1, nảy lên theo beat rồi rơi
        self._pulse_phase = 0.0
        self._sparkle_pts = []      # vị trí hạt lấp lánh (toạ độ tương đối)
        
        if self._svg_content:
            try:
                from PySide6.QtSvg import QSvgRenderer
                from PySide6.QtCore import QByteArray
                self._svg_renderer = QSvgRenderer()
                self._svg_renderer.load(QByteArray(self._svg_content.encode('utf-8')))
            except Exception as e:
                print(f"Failed to load SVG in PainterButton: {e}")

        self.setFixedHeight(height)
        if fixed_width:
            self.setFixedWidth(fixed_width)
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        else:
            self.setMinimumWidth(50 if not self._svg_content else height)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.setCursor(Qt.PointingHandCursor)

    # ── Public API ───────────────────────────────────────────
    def text(self): return self._text
    def setText(self, t): self._text = t; self.update()
    def setEnabled(self, e):
        self._enabled = e
        self.setCursor(Qt.PointingHandCursor if e else Qt.ForbiddenCursor)
        self.update()
    def isEnabled(self): return self._enabled
    def setActive(self, a): self._active = a; self.update()

    # ── Lấp lánh theo nhạc (Premium) ─────────────────────────
    def set_music_reactive(self, on: bool):
        """Bật/tắt hiệu ứng glow + lấp lánh nảy theo beat (dùng AudioPulse chung)."""
        on = bool(on)
        if on == self._music_reactive:
            return
        self._music_reactive = on
        try:
            from ui.components.audio_pulse import AudioPulse
            ap = AudioPulse.instance()
            if on:
                # Vị trí hạt lấp lánh cố định quanh nút (toạ độ tương đối 0..1).
                rnd = random.Random(id(self) & 0xFFFF)
                self._sparkle_pts = [
                    (rnd.uniform(0.10, 0.90), rnd.uniform(0.12, 0.88), rnd.uniform(0, math.tau))
                    for _ in range(3)
                ]
                ap.pulse.connect(self._on_pulse)
                ap.start()
            else:
                try:
                    ap.pulse.disconnect(self._on_pulse)
                except Exception:
                    pass
                ap.stop()
                self._pulse_glow = 0.0
                self.update()
        except Exception as e:
            print(f"[PainterButton] music reactive lỗi: {e}")
            self._music_reactive = False

    def _on_pulse(self, level: float, beat: bool):
        if not self._music_reactive:
            return
        prev = self._pulse_glow
        glow = self._pulse_glow * 0.82
        glow = max(glow, level * 0.45)      # nền lung linh theo độ to
        if beat:
            glow = min(1.0, glow + 0.6)      # nảy mạnh khi có beat
        self._pulse_glow = glow
        self._pulse_phase += 0.4
        # Chỉ repaint khi đáng kể (tiết kiệm) — hoặc khi vừa tắt hẳn.
        if glow > 0.03 or prev > 0.03:
            self.update()

    def setSvg(self, svg_content: str):
        """Thay thế SVG icon tại runtime và repaint."""
        self._svg_content = svg_content
        try:
            from PySide6.QtSvg import QSvgRenderer
            from PySide6.QtCore import QByteArray
            if self._svg_renderer is None:
                self._svg_renderer = QSvgRenderer()
            self._svg_renderer.load(QByteArray(svg_content.encode('utf-8')))
        except Exception as e:
            print(f"setSvg failed: {e}")
        self.update()

    def setStyleSheet(self, qss):
        """Accept but ignore QSS - we paint ourselves. Parse color if present."""
        # Try to extract background-color from QSS for backward compat
        import re
        m = re.search(r'background-color:\s*(#[0-9a-fA-F]{6})', qss)
        if m:
            self._color = QColor(m.group(1))
            self.update()

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = self._radius
        rect = QRectF(1, 1, w - 2, h - 2)

        base = QColor(self._color)
        if not self._enabled:
            base = QColor(C["card_hover"])

        # ── Outer glow (hover) ───────────────────────────────
        if self._hover and self._enabled:
            glow = QColor(base)
            glow.setAlpha(40)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(QRectF(0, 0, w, h), r + 2, r + 2)

        # ── Body gradient ────────────────────────────────────
        grad = QLinearGradient(0, 0, 0, h)
        if self._pressed and self._enabled:
            # Pressed: darker, inverted gradient
            grad.setColorAt(0.0, self._darken(base, 0.15))
            grad.setColorAt(0.5, self._darken(base, 0.05))
            grad.setColorAt(1.0, base)
        elif self._hover and self._enabled:
            # Hover: brighter
            grad.setColorAt(0.0, self._lighten(base, 0.2))
            grad.setColorAt(0.5, self._lighten(base, 0.08))
            grad.setColorAt(1.0, base)
        else:
            grad.setColorAt(0.0, self._lighten(base, 0.12))
            grad.setColorAt(0.5, base)
            grad.setColorAt(1.0, self._darken(base, 0.12))

        # Border
        border_color = QColor(base)
        if self._hover and self._enabled:
            border_color = self._lighten(base, 0.35)
            border_color.setAlpha(200)
        else:
            border_color.setAlpha(50)

        p.setPen(QPen(border_color, 1))
        p.setBrush(grad)
        p.drawRoundedRect(rect, r, r)

        # ── Top highlight (3D) ───────────────────────────────
        if not self._pressed:
            hi = QLinearGradient(0, 1, 0, h * 0.4)
            hi.setColorAt(0, QColor(255, 255, 255, 35 if self._enabled else 10))
            hi.setColorAt(1, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(hi)
            hi_rect = QRectF(2, 1, w - 4, h * 0.4)
            p.drawRoundedRect(hi_rect, r - 1, r - 1)

        # ── Text or SVG ─────────────────────────────────────────────
        text_color = QColor("#FFFFFF") if self._enabled else QColor(C["text_muted"])
        
        if self._svg_renderer:
            # Draw SVG
            size = self._svg_size
            cx, cy = w / 2, h / 2
            svg_rect = QRectF(cx - size / 2, cy - size / 2, size, size)
            if self._pressed:
                svg_rect.translate(1, 1)
                
            if not self._enabled:
                p.setOpacity(0.5)
            self._svg_renderer.render(p, svg_rect)
            if not self._enabled:
                p.setOpacity(1.0)
        else:
            font = QFont()
            font.setFamily("Segoe UI")
            font.setPixelSize(self._font_size)
            font.setBold(True)
            p.setFont(font)
    
            if self._pressed:
                # Slight offset for pressed feel
                p.setPen(text_color)
                p.drawText(QRectF(1, 1, w, h), Qt.AlignCenter, self._text)
            else:
                # Text shadow
                shadow_c = QColor(0, 0, 0, 60)
                p.setPen(shadow_c)
                p.drawText(QRectF(1, 1, w, h), Qt.AlignCenter, self._text)
                p.setPen(text_color)
                p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self._text)

        # ── Active LED Indicator ──
        if self._active:
            p.setPen(Qt.NoPen)
            # Outer glow
            glow = QColor(base)
            glow.setAlpha(120)
            p.setBrush(glow)
            p.drawEllipse(QRectF(w - 11, 4, 8, 8))
            # Inner white dot
            p.setBrush(QColor(255, 255, 255))
            p.drawEllipse(QRectF(w - 9, 6, 4, 4))

        # ── Lấp lánh theo nhạc (Premium) ─────────────────────
        if self._music_reactive and self._pulse_glow > 0.03 and self._enabled:
            self._paint_music_glow(p, w, h, r)

        p.end()

    def _paint_music_glow(self, p, w, h, r):
        g = self._pulse_glow
        base = QColor(self._color)
        # Viền neon sáng theo beat
        ring = QColor(self._lighten(base, 0.4))
        ring.setAlpha(int(220 * g))
        p.setPen(QPen(ring, 1.5 + 1.5 * g))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(1.5, 1.5, w - 3, h - 3), r, r)
        # Quầng sáng mềm ngoài viền
        halo = QColor(base)
        halo.setAlpha(int(70 * g))
        p.setPen(QPen(halo, 3))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r + 1, r + 1)
        # Hạt lấp lánh nhấp nháy
        p.setPen(Qt.NoPen)
        for sx, sy, off in self._sparkle_pts:
            tw = 0.5 + 0.5 * math.sin(self._pulse_phase + off)
            a = int(230 * g * tw)
            if a < 12:
                continue
            px, py = sx * w, sy * h
            sz = 1.2 + 2.0 * g * tw
            glow = QRadialGradient(px, py, sz * 2.6)
            glow.setColorAt(0.0, QColor(255, 255, 255, a))
            glow.setColorAt(1.0, QColor(self._color.red(), self._color.green(), self._color.blue(), 0))
            p.setBrush(glow)
            p.drawEllipse(QPointF(px, py), sz * 2.6, sz * 2.6)
            p.setBrush(QColor(255, 255, 255, a))
            p.drawEllipse(QPointF(px, py), sz * 0.5, sz * 0.5)

    # ── Mouse events ─────────────────────────────────────────
    def mousePressEvent(self, e):
        if self._enabled and e.button() == Qt.LeftButton:
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, e):
        if self._pressed and self._enabled:
            self._pressed = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._pressed = False
        self.update()

    # ── Color helpers ────────────────────────────────────────
    @staticmethod
    def _lighten(color, factor=0.2):
        c = QColor(color)
        r = min(255, int(c.red()   + (255 - c.red())   * factor))
        g = min(255, int(c.green() + (255 - c.green()) * factor))
        b = min(255, int(c.blue()  + (255 - c.blue())  * factor))
        return QColor(r, g, b, c.alpha())

    @staticmethod
    def _darken(color, factor=0.2):
        c = QColor(color)
        r = max(0, int(c.red()   * (1 - factor)))
        g = max(0, int(c.green() * (1 - factor)))
        b = max(0, int(c.blue()  * (1 - factor)))
        return QColor(r, g, b, c.alpha())
