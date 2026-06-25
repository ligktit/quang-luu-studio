"""
ui.components.premium_tag
=========================
Tag "PREMIUM" dạng text với **texture kim cương** (diamond):

- Chữ đổ gradient băng giá glassy (icy-white → xanh nhạt → bạc) tạo cảm giác mặt
  cắt kim cương, kèm đường facet sáng + viền tối cho nổi trên nền.
- Ánh **sheen** trắng quét chéo qua chữ (clip theo nét chữ) → lấp lánh.
- Vài hạt **sparkle** nhấp nháy + một viên kim cương nhỏ (faceted gem) bên trái.
- Nền pill tối, viền gradient sang trọng.

Tự đo kích thước theo text. Animation nhẹ bằng QTimer (~30fps).
"""
from __future__ import annotations

import math

from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QFontMetrics, QPainterPath,
    QLinearGradient, QRadialGradient, QPolygonF,
)


class PremiumTag(QWidget):
    def __init__(self, text: str = "PREMIUM", parent=None, height: int = 26, font_size: int = 13):
        super().__init__(parent)
        self._text = text
        self._h = height
        self._fs = font_size
        self._phase = 0.0
        self._sheen = -0.3
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self._font = QFont("Segoe UI", self._fs)
        self._font.setBold(True)
        self._font.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)

        fm = QFontMetrics(self._font)
        self._gem = self._h - 12                       # cạnh viên kim cương
        self._pad_l = 12 + self._gem + 8               # chừa chỗ cho gem
        text_w = fm.horizontalAdvance(self._text)
        self.setFixedSize(self._pad_l + text_w + 16, self._h)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def setText(self, t: str):
        self._text = t
        self.update()

    def _tick(self):
        self._phase += 0.08
        # Sheen quét rồi nghỉ một nhịp (tạo "chớp" định kỳ)
        self._sheen += 0.018
        if self._sheen > 1.6:
            self._sheen = -0.3
        self.update()

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            self._paint_pill(p, w, h)
            self._paint_gem(p)
            self._paint_text(p, w, h)
            p.end()
        except Exception:
            pass

    def _paint_pill(self, p, w, h):
        rect = QRectF(0.5, 0.5, w - 1, h - 1)
        r = h / 2
        # Nền tối hơi tím
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(28, 34, 58, 235))
        bg.setColorAt(1.0, QColor(16, 20, 38, 240))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(rect, r, r)
        # Viền gradient kim cương
        bd = QLinearGradient(0, 0, w, 0)
        bd.setColorAt(0.0, QColor(180, 230, 255, 200))
        bd.setColorAt(0.5, QColor(120, 180, 230, 120))
        bd.setColorAt(1.0, QColor(210, 240, 255, 180))
        p.setPen(QPen(bd, 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, r, r)

    def _paint_gem(self, p):
        """Viên kim cương nhỏ faceted bên trái."""
        s = self._gem
        cx = 10 + s / 2
        cy = self.height() / 2
        top = cy - s / 2
        bot = cy + s / 2
        # Hình thoi (gem) với mặt bàn (table) phía trên
        table = s * 0.30
        outline = QPolygonF([
            QPointF(cx - table, top),
            QPointF(cx + table, top),
            QPointF(cx + s / 2, cy - s * 0.12),
            QPointF(cx, bot),
            QPointF(cx - s / 2, cy - s * 0.12),
        ])
        grad = QLinearGradient(cx, top, cx, bot)
        grad.setColorAt(0.0, QColor(225, 245, 255))
        grad.setColorAt(0.5, QColor(150, 210, 245))
        grad.setColorAt(1.0, QColor(90, 150, 210))
        p.setPen(QPen(QColor(230, 248, 255, 220), 0.8))
        p.setBrush(grad)
        p.drawPolygon(outline)
        # Đường facet
        p.setPen(QPen(QColor(255, 255, 255, 140), 0.8))
        p.drawLine(QPointF(cx - table, top), QPointF(cx, cy - s * 0.12))
        p.drawLine(QPointF(cx + table, top), QPointF(cx, cy - s * 0.12))
        p.drawLine(QPointF(cx - s / 2, cy - s * 0.12), QPointF(cx, cy - s * 0.12))
        p.drawLine(QPointF(cx + s / 2, cy - s * 0.12), QPointF(cx, cy - s * 0.12))
        p.drawLine(QPointF(cx, cy - s * 0.12), QPointF(cx, bot))
        # Lấp lánh trên gem
        tw = 0.5 + 0.5 * math.sin(self._phase * 1.6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, int(200 * tw)))
        p.drawEllipse(QPointF(cx - table * 0.3, top + s * 0.18), 1.3, 1.3)

    def _paint_text(self, p, w, h):
        fm = QFontMetrics(self._font)
        x = self._pad_l
        baseline = (h + fm.ascent() - fm.descent()) / 2

        path = QPainterPath()
        path.addText(QPointF(x, baseline), self._font, self._text)

        # Bóng đổ nhẹ cho nổi trên nền
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.translate(0.8, 1.0)
        p.drawPath(path)
        p.translate(-0.8, -1.0)

        # Texture kim cương: gradient dọc nhiều mặt cắt
        grad = QLinearGradient(0, baseline - fm.ascent(), 0, baseline)
        grad.setColorAt(0.00, QColor(236, 250, 255))
        grad.setColorAt(0.32, QColor(255, 255, 255))
        grad.setColorAt(0.50, QColor(178, 222, 250))   # mặt xanh nhạt
        grad.setColorAt(0.56, QColor(255, 255, 255))   # facet sáng sắc
        grad.setColorAt(0.74, QColor(150, 196, 230))
        grad.setColorAt(1.00, QColor(214, 238, 255))
        p.setBrush(grad)
        p.drawPath(path)

        # Viền mảnh tăng độ sắc của chữ
        p.setPen(QPen(QColor(120, 170, 215, 150), 0.7))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # Ánh sheen quét chéo — clip theo nét chữ
        if -0.3 <= self._sheen <= 1.3:
            p.save()
            p.setClipPath(path)
            band = self._sheen * (w + 80) - 40
            sheen = QLinearGradient(band - 26, 0, band + 26, h)
            sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
            sheen.setColorAt(0.5, QColor(255, 255, 255, 200))
            sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(sheen)
            p.drawRect(QRectF(0, 0, w, h))
            p.restore()

        # Sparkle nhấp nháy ở 2 điểm cố định trên chữ
        for fx, off in ((0.5, 0.0), (0.86, 2.1)):
            tw = 0.5 + 0.5 * math.sin(self._phase * 2.0 + off)
            if tw < 0.2:
                continue
            sx = x + (w - x - 8) * fx
            sy = baseline - fm.ascent() * 0.62
            a = int(235 * tw)
            glow = QRadialGradient(sx, sy, 4)
            glow.setColorAt(0.0, QColor(255, 255, 255, a))
            glow.setColorAt(1.0, QColor(180, 225, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QPointF(sx, sy), 4, 4)
            # Tia chữ thập
            p.setPen(QPen(QColor(255, 255, 255, a), 0.9))
            ray = 3.2 * tw
            p.drawLine(QPointF(sx - ray, sy), QPointF(sx + ray, sy))
            p.drawLine(QPointF(sx, sy - ray), QPointF(sx, sy + ray))

    def stop(self):
        self._timer.stop()
