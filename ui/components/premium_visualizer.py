"""
ui.components.premium_visualizer
================================
Dải visualizer cao cấp cho người dùng **Premium**: thanh phổ phản ứng âm thanh
(audio-reactive bars) + lớp hạt **lấp lánh** (sparkle) + ánh sheen quét ngang.

Thiết kế:
- Tự bắt audio loopback (WASAPI) nhẹ để bar nhảy theo nhạc; fail-soft → animation
  sine khi không có audio (vẫn lung linh).
- Hạt lấp lánh: chấm sáng nhấp nháy (alpha sine) trôi nhẹ lên, tự tái sinh.
- Chỉ thêm vào layout khi `entitlements.is_premium()` (gọi ở frontend).

Self-contained: KHÔNG import frontend_qt (tránh circular). Dừng bằng stop().
"""
import math
import random
import threading

import numpy as np
from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QLinearGradient, QRadialGradient, QBrush

# Bảng màu gradient (teal → tím → hồng) — đồng bộ design tokens.
_C1 = (56, 189, 248)    # teal
_C2 = (168, 85, 247)    # purple
_C3 = (236, 72, 153)    # pink


def _lerp_color(t: float):
    """Nội suy màu theo t∈[0,1] qua 3 chặng teal→tím→hồng."""
    if t < 0.5:
        tt = t * 2
        a, b = _C1, _C2
    else:
        tt = (t - 0.5) * 2
        a, b = _C2, _C3
    return (
        int(a[0] + (b[0] - a[0]) * tt),
        int(a[1] + (b[1] - a[1]) * tt),
        int(a[2] + (b[2] - a[2]) * tt),
    )


class _Sparkle:
    """Một hạt lấp lánh: vị trí tương đối (0..1), pha nhấp nháy, tốc độ trôi."""
    __slots__ = ("x", "y", "phase", "speed", "size", "twinkle", "hue")

    def __init__(self, w_rand=random):
        self.reset(w_rand, first=True)

    def reset(self, r=random, first=False):
        self.x = r.random()
        self.y = r.random() if first else 1.05  # tái sinh từ đáy
        self.phase = r.uniform(0, math.tau)
        self.speed = r.uniform(0.0015, 0.006)
        self.size = r.uniform(1.2, 3.0)
        self.twinkle = r.uniform(1.5, 3.5)
        # Màu: phần lớn trắng/vàng nhạt, đôi khi teal/hồng
        self.hue = r.choice([
            (255, 255, 255), (255, 240, 200), (255, 240, 200),
            (180, 230, 255), (255, 200, 235),
        ])


class PremiumVisualizer(QWidget):
    """Dải visualizer + sparkle cho Premium. Cao cố định, full-width."""

    _audio_ready = Signal()

    BAR_COUNT = 72
    SPARKLE_COUNT = 46
    POINTS = 256

    def __init__(self, parent=None, height: int = 92):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(height)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self._phase = 0.0
        self._sheen = 0.0
        self._buffer = np.zeros(self.POINTS, dtype=np.float32)
        self._peaks = [0.0] * self.BAR_COUNT      # đỉnh rơi chậm
        self._sparkles = [_Sparkle() for _ in range(self.SPARKLE_COUNT)]

        # Nguồn audio dùng chung (1 capture cho cả visualizer lẫn nút lấp lánh).
        try:
            from ui.components.audio_pulse import AudioPulse
            self._pulse = AudioPulse.instance()
            self._pulse.start()
        except Exception:
            self._pulse = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30fps

    def stop(self):
        self._timer.stop()
        if self._pulse is not None:
            try:
                self._pulse.stop()
            except Exception:
                pass

    # ── Animation tick ───────────────────────────────────────
    def _tick(self):
        if self._pulse is not None:
            self._buffer = self._pulse.latest_buffer()
        self._phase += 0.05
        self._sheen = (self._sheen + 0.006) % 1.4   # quét rồi nghỉ
        for s in self._sparkles:
            s.y -= s.speed
            if s.y < -0.05:
                s.reset()
        # Peak rơi chậm
        for i in range(self.BAR_COUNT):
            self._peaks[i] = max(0.0, self._peaks[i] - 0.02)
        self.update()

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            self._paint_bg(p, w, h)
            self._paint_bars(p, w, h)
            self._paint_sparkles(p, w, h)
            self._paint_sheen(p, w, h)
            p.end()
        except Exception:
            pass  # vẽ không bao giờ được làm crash app

    def _paint_bg(self, p, w, h):
        p.setPen(Qt.NoPen)
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(14, 18, 34, 235))
        bg.setColorAt(1.0, QColor(8, 11, 24, 245))
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)
        # Glow trung tâm pulsing nhẹ
        pulse = 0.5 + 0.5 * math.sin(self._phase * 0.6)
        glow = QRadialGradient(w / 2, h * 0.5, w * 0.55)
        glow.setColorAt(0.0, QColor(120, 90, 240, int(14 + 10 * pulse)))
        glow.setColorAt(0.6, QColor(56, 189, 248, 6))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setBrush(glow)
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)
        # Viền gradient
        bd = QLinearGradient(0, 0, w, 0)
        bd.setColorAt(0.0, QColor(*_C1, 60))
        bd.setColorAt(0.5, QColor(*_C2, 45))
        bd.setColorAt(1.0, QColor(*_C3, 40))
        p.setPen(QPen(QBrush(bd), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 12, 12)

    def _paint_bars(self, p, w, h):
        margin = 18
        usable = w - margin * 2
        gap = 3
        bw = max(2.0, (usable - gap * (self.BAR_COUNT - 1)) / self.BAR_COUNT)
        cy = h * 0.5
        max_half = h * 0.40
        buf = self._buffer
        has_audio = bool(np.max(np.abs(buf)) > 0.001)
        step = self.POINTS / self.BAR_COUNT

        p.setPen(Qt.NoPen)
        for i in range(self.BAR_COUNT):
            if has_audio:
                idx = int(i * step)
                amp = min(1.0, float(np.abs(buf[idx])) * 1.7) if idx < len(buf) else 0.0
            else:
                t = i / (self.BAR_COUNT - 1)
                env = math.sin(math.pi * t)
                amp = abs(env * (
                    0.34 * math.sin(self._phase * 1.0 + i * 0.22) +
                    0.20 * math.sin(self._phase * 1.7 + i * 0.40) +
                    0.10 * math.sin(self._phase * 2.7 + i * 0.65)
                ))
            amp = max(0.0, min(1.0, amp))
            self._peaks[i] = max(self._peaks[i], amp)

            t = i / (self.BAR_COUNT - 1)
            r, g, b = _lerp_color(t)
            half = max(2.0, amp * max_half)
            x = margin + i * (bw + gap)

            # Glow halo phía sau thanh cao
            if amp > 0.25:
                halo = QColor(r, g, b, int(40 * amp))
                p.setBrush(halo)
                hw = bw + 6
                p.drawRoundedRect(QRectF(x - 3, cy - half - 3, hw, half * 2 + 6),
                                  hw / 2, hw / 2)

            # Thanh chính: gradient dọc sáng giữa
            alpha = int(110 + amp * 145)
            grad = QLinearGradient(x, cy - half, x, cy + half)
            grad.setColorAt(0.0, QColor(r, g, b, alpha))
            grad.setColorAt(0.5, QColor(min(255, r + 70), min(255, g + 70), min(255, b + 70), alpha))
            grad.setColorAt(1.0, QColor(r, g, b, int(alpha * 0.55)))
            p.setBrush(grad)
            rad = min(bw / 2, 2.5)
            p.drawRoundedRect(QRectF(x, cy - half, bw, half * 2), rad, rad)

            # Đỉnh (peak cap) rơi chậm — chấm sáng
            peak_half = self._peaks[i] * max_half
            if peak_half > half + 2:
                p.setBrush(QColor(255, 255, 255, 150))
                p.drawRoundedRect(QRectF(x, cy - peak_half - 1, bw, 2), 1, 1)

    def _paint_sparkles(self, p, w, h):
        p.setPen(Qt.NoPen)
        for s in self._sparkles:
            tw = 0.5 + 0.5 * math.sin(self._phase * s.twinkle + s.phase)
            if tw < 0.05:
                continue
            px = s.x * w
            py = s.y * h
            r, g, b = s.hue
            sz = s.size * (0.6 + 0.8 * tw)
            # Glow tròn
            a = int(180 * tw)
            glow = QRadialGradient(px, py, sz * 3)
            glow.setColorAt(0.0, QColor(r, g, b, a))
            glow.setColorAt(1.0, QColor(r, g, b, 0))
            p.setBrush(glow)
            p.drawEllipse(QPointF(px, py), sz * 3, sz * 3)
            # Lõi sáng + tia chữ thập (cảm giác lấp lánh)
            p.setBrush(QColor(255, 255, 255, a))
            p.drawEllipse(QPointF(px, py), sz * 0.6, sz * 0.6)
            pen = QPen(QColor(r, g, b, int(a * 0.7)), 1.0)
            p.setPen(pen)
            ray = sz * 2.4
            p.drawLine(QPointF(px - ray, py), QPointF(px + ray, py))
            p.drawLine(QPointF(px, py - ray), QPointF(px, py + ray))
            p.setPen(Qt.NoPen)

    def _paint_sheen(self, p, w, h):
        """Dải sáng quét chéo (chỉ hiện khi sheen<1, rồi nghỉ)."""
        if self._sheen >= 1.0:
            return
        pos = self._sheen
        cx = pos * (w + 160) - 80
        sheen = QLinearGradient(cx - 60, 0, cx + 60, h)
        sheen.setColorAt(0.0, QColor(255, 255, 255, 0))
        sheen.setColorAt(0.5, QColor(255, 255, 255, 22))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(sheen)
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)
