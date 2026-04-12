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

import time
import unicodedata

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPen
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
        painter.end()
