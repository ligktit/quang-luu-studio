"""
ui.components.marquee
=====================
Sleek, transparent seamless marquee label.

Features:
  - Transparent background to fit tightly into Glass panels/trays.
  - Status glowing icon on the left based on text content.
  - Smooth float-based text scrolling.
  - Linear gradient fade masks on both edges of the scrolling lane.
  - Pause on hover.
  - Very clean, no chips or blocky backgrounds.
"""
from __future__ import annotations

import math
import time
import unicodedata

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget
from ui.design_tokens import C


class SmoothMarqueeLabel(QWidget):
    """Sleek seamless rolling marquee with glowing status."""

    ICON_SIZE = 18
    ICON_PAD = 12
    EDGE_FADE = 40
    LOOP_GAP = 50
    FONT_PX = 14
    STATUS_FONT_PX = 11
    DEFAULT_HEIGHT = 36

    def __init__(self, text: str, color: str = "#fc8403", speed: int = 70, fps: int = 60, parent=None):
        super().__init__(parent)
        self.text = text or ""
        self._accent = QColor(color)
        self._speed = speed
        self._fps = max(24, fps)
        self._hovered = False
        self._offset = 0.0
        self._ready = False
        self._last_tick = None
        self._text_width = 0.0
        self._status = {"glyph": "\u266A", "label": "Now", "accent": QColor(self._accent)}

        # Vi\u1EC1n LED ch\u1EA1y (VIP). T\u1EAFt m\u1EB7c \u0111\u1ECBnh \u2014 b\u1EADt qua set_led_border(True).
        self._led_border = False
        self._led_phase = 0.0

        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(180)
        self.setMinimumHeight(self.DEFAULT_HEIGHT)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(max(1, int(1000 / self._fps)))

        self._update_content_metrics(reset_offset=True)

    def sizeHint(self) -> QSize:
        return QSize(420, self.DEFAULT_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(220, self.DEFAULT_HEIGHT)

    def set_text(self, text: str):
        normalized = text or ""
        if normalized == self.text:
            return
        self.text = normalized
        self._update_content_metrics(reset_offset=True)
        self.update()

    def setText(self, text: str):
        self.set_text(text)

    def set_color(self, color: str):
        self._accent = QColor(color)
        self._status = self._infer_status(self.text)
        self.update()

    def set_led_border(self, on: bool):
        """Bật/tắt viền LED chạy (dành cho khách VIP/Premium)."""
        self._led_border = bool(on)
        # Chừa lề để bóng LED không đè chữ; cao tối thiểu lớn hơn chút.
        self.setMinimumHeight(self.DEFAULT_HEIGHT + (6 if self._led_border else 0))
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._last_tick = time.perf_counter()
        self.update()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        self._ready = False
        self._last_tick = None
        super().resizeEvent(event)

    def _font(self) -> QFont:
        font = QFont("Segoe UI")
        font.setPixelSize(self.FONT_PX)
        font.setWeight(QFont.DemiBold)
        return font

    def _status_font(self) -> QFont:
        font = QFont("Segoe UI")
        font.setPixelSize(self.STATUS_FONT_PX)
        font.setWeight(QFont.Bold)
        return font

    def _normalize_key(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text or "")
        return normalized.encode("ascii", "ignore").decode("ascii").lower()

    def _infer_status(self, text: str) -> dict[str, QColor]:
        lower = self._normalize_key(text)
        accent = QColor(self._accent)
        if "dang do" in lower or "scan" in lower:
            return {"glyph": "\u21BB", "label": "Scan", "accent": QColor("#f59e0b")}
        if "ban quyen" in lower or "quang luu studio" in lower:
            return {"glyph": "\u2726", "label": "Brand", "accent": QColor(C["teal"])}
        return {"glyph": "\u266A", "label": "Live", "accent": accent}

    def _update_content_metrics(self, reset_offset: bool):
        self._status = self._infer_status(self.text)
        fm = QFontMetricsF(self._font())
        self._text_width = fm.horizontalAdvance(self.text)
        self._last_tick = None
        if reset_offset:
            self._ready = False

    def _content_rect(self) -> QRectF:
        start_x = self.ICON_SIZE + (self.ICON_PAD * 2)
        return QRectF(start_x, 0, max(10.0, self.width() - start_x), self.height())

    # ── Cycle helper ─────────────────────────────────────────────────────────
    # Khoảng cách giữa điểm đầu của 2 bản text.
    # Chọn max(lane_width / 2, text_width + LOOP_GAP) để:
    #   • Khi text ngắn  → 2 bản trải đều cách nhau lane_width / 2
    #   • Khi text dài   → giữ khoảng cách tối thiểu = text_width + LOOP_GAP
    MAX_TEXT_REPEATS = 2

    def _cycle(self) -> float:
        lane_w = self._content_rect().width()
        even   = lane_w / self.MAX_TEXT_REPEATS         # chia đều cho 2
        min_gap = self._text_width + self.LOOP_GAP      # khoảng cách tối thiểu
        return max(even, min_gap)

    def _reset_offset(self):
        self._offset = self._content_rect().width()
        self._ready = True

    def _tick(self):
        if self.width() <= 0:
            return

        # Viền LED chạy liên tục, kể cả khi hover (text dừng nhưng đèn vẫn nhấp nháy).
        if self._led_border:
            self._led_phase += 0.05
            self.update()

        if not self._ready:
            self._reset_offset()
            self.update()
            return

        now = time.perf_counter()
        if self._last_tick is None:
            self._last_tick = now
            return

        delta = min(now - self._last_tick, 0.05)
        self._last_tick = now

        if self._hovered or self._text_width <= 0:
            return

        # Continuous loop logic — dùng _cycle() để đồng bộ với paintEvent
        cycle = self._cycle()
        self._offset -= self._speed * delta
        if self._offset <= -cycle:
            self._offset += cycle
        self.update()

    def _draw_status_icon(self, painter: QPainter):
        accent = QColor(self._status["accent"])
        
        icon_rect = QRectF(
            self.ICON_PAD,
            (self.height() - self.ICON_SIZE) / 2,
            self.ICON_SIZE,
            self.ICON_SIZE,
        )

        painter.setPen(Qt.NoPen)
        accent_bg = QColor(accent)
        accent_bg.setAlpha(40 if not self._hovered else 60)
        painter.setBrush(accent_bg)
        painter.drawEllipse(icon_rect)

        # Pulse ring
        painter.setPen(QPen(accent, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(icon_rect)

        # Glowing dot if recording/live
        pulse_rect = QRectF(icon_rect.right() - 4, icon_rect.top() - 1, 5, 5)
        painter.setPen(Qt.NoPen)
        painter.setBrush(accent)
        painter.drawEllipse(pulse_rect)

        # Glyph
        painter.setPen(QColor(C["text"]))
        painter.setFont(self._status_font())
        painter.drawText(icon_rect, Qt.AlignCenter, self._status["glyph"])

    # ── Viền LED chạy (VIP) ──────────────────────────────────────────────────
    def _round_rect_point(self, rect: QRectF, r: float, d: float, perim: float):
        """Toạ độ tại quãng đường d (đi dọc chu vi pill/rounded-rect)."""
        x0, y0, w, h = rect.left(), rect.top(), rect.width(), rect.height()
        sx = max(0.0, w - 2 * r)          # đoạn thẳng ngang
        sy = max(0.0, h - 2 * r)          # đoạn thẳng dọc
        arc = (math.pi / 2.0) * r          # 1/4 cung
        cx_l, cx_r = x0 + r, x0 + w - r
        cy_t, cy_b = y0 + r, y0 + h - r
        segs = [sx, arc, sy, arc, sx, arc, sy, arc]
        d = d % perim
        for i, seg in enumerate(segs):
            if d <= seg or i == len(segs) - 1:
                if i == 0:      # top L→R
                    return cx_l + d, y0
                if i == 1:      # corner TR
                    th = -math.pi / 2 + (d / max(arc, 1e-6)) * (math.pi / 2)
                    return cx_r + r * math.cos(th), cy_t + r * math.sin(th)
                if i == 2:      # right T→B
                    return x0 + w, cy_t + d
                if i == 3:      # corner BR
                    th = 0 + (d / max(arc, 1e-6)) * (math.pi / 2)
                    return cx_r + r * math.cos(th), cy_b + r * math.sin(th)
                if i == 4:      # bottom R→L
                    return cx_r - d, y0 + h
                if i == 5:      # corner BL
                    th = math.pi / 2 + (d / max(arc, 1e-6)) * (math.pi / 2)
                    return cx_l + r * math.cos(th), cy_b + r * math.sin(th)
                if i == 6:      # left B→T
                    return x0, cy_b - d
                # corner TL
                th = math.pi + (d / max(arc, 1e-6)) * (math.pi / 2)
                return cx_l + r * math.cos(th), cy_t + r * math.sin(th)
            d -= seg
        return x0, y0

    def _draw_led_border(self, painter: QPainter):
        inset = 3.0
        rect = QRectF(inset, inset, self.width() - inset * 2, self.height() - inset * 2)
        if rect.width() <= 4 or rect.height() <= 4:
            return
        r = rect.height() / 2.0                       # dạng pill (bảng hiệu)
        perim = 2 * max(0.0, rect.width() - 2 * r) + 2 * math.pi * r

        # Viền nền vàng mờ (ambiance) — 2 lớp tạo quầng sáng.
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 196, 64, 28), 4.0))
        painter.drawRoundedRect(rect, r, r)
        painter.setPen(QPen(QColor(255, 224, 150, 70), 1.4))
        painter.drawRoundedRect(rect, r, r)

        # Bóng LED chạy quanh chu vi.
        spacing = 13.0
        count = max(12, int(perim / spacing))
        loops = 3.0                                   # số cụm sáng chạy quanh
        painter.setPen(Qt.NoPen)
        for i in range(count):
            t = i / count
            x, y = self._round_rect_point(rect, r, t * perim, perim)
            # Sóng sáng chạy: pha dịch theo _led_phase.
            b = 0.5 + 0.5 * math.sin(t * loops * math.tau - self._led_phase * math.tau)
            b = b * b                                 # nén để các bóng tắt rõ hơn
            if b < 0.04:
                continue
            # Màu vàng gold → trắng nóng khi sáng nhất.
            cr = int(255)
            cg = int(190 + 60 * b)
            cb = int(70 + 150 * b)
            core = QColor(cr, min(255, cg), min(255, cb))
            # Quầng glow
            gr = 2.5 + 5.0 * b
            glow = QRadialGradient(x, y, gr)
            ga = int(200 * b)
            glow.setColorAt(0.0, QColor(cr, min(255, cg), min(255, cb), ga))
            glow.setColorAt(1.0, QColor(cr, min(255, cg), 80, 0))
            painter.setBrush(glow)
            painter.drawEllipse(QRectF(x - gr, y - gr, gr * 2, gr * 2))
            # Lõi bóng
            cs = 1.1 + 1.3 * b
            painter.setBrush(core)
            painter.drawEllipse(QRectF(x - cs, y - cs, cs * 2, cs * 2))

    def paintEvent(self, _):
        if self.width() <= 0 or self.height() <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        self._draw_status_icon(painter)

        lane = self._content_rect()
        painter.save()
        painter.setClipRect(lane)

        # Cycle = khoảng cách đều giữa 2 bản text (đồng bộ với _tick)
        cycle   = self._cycle()
        start_x = lane.left() + self._offset

        painter.setFont(self._font())
        text_color = QColor(self._status["accent"]) if self._hovered else QColor(C["text"])
        painter.setPen(text_color)

        drawn = 0
        while start_x < lane.right() and drawn < self.MAX_TEXT_REPEATS:
            text_rect = QRectF(start_x, 0, self._text_width, lane.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text)
            drawn += 1
            if cycle <= 0:
                break
            start_x += cycle

        # Left/Right Fades
        base_bg = QColor(14, 19, 34) # Matches PaintedHeaderBar tray color approx (or transparent -> solid bg color)
        
        left_grad = QLinearGradient(lane.left(), 0, lane.left() + self.EDGE_FADE, 0)
        left_grad.setColorAt(0.0, QColor(base_bg.red(), base_bg.green(), base_bg.blue(), 255))
        left_grad.setColorAt(1.0, QColor(base_bg.red(), base_bg.green(), base_bg.blue(), 0))

        right_grad = QLinearGradient(lane.right() - self.EDGE_FADE, 0, lane.right(), 0)
        right_grad.setColorAt(0.0, QColor(base_bg.red(), base_bg.green(), base_bg.blue(), 0))
        right_grad.setColorAt(1.0, QColor(base_bg.red(), base_bg.green(), base_bg.blue(), 255))

        painter.setPen(Qt.NoPen)
        painter.setBrush(left_grad)
        painter.drawRect(QRectF(lane.left(), 0, self.EDGE_FADE, lane.height()))

        painter.setBrush(right_grad)
        painter.drawRect(QRectF(lane.right() - self.EDGE_FADE, 0, self.EDGE_FADE, lane.height()))

        painter.restore()

        # Viền LED VIP — vẽ trên cùng, ngoài vùng clip của lane.
        if self._led_border:
            self._draw_led_border(painter)

        painter.end()
