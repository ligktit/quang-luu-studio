"""
ui.components.waveform_hero
==============================
Full-width waveform hero panel — the visual centerpiece.

Features:
  - Real-time WASAPI loopback audio capture → waveform
  - Gradient fill (teal → purple → pink) with mirror reflection
  - Overlay: song title, key badge, BPM
  - Overlay: MIDI status ring, Auto-Tune toggle, Score ring
  - Transport bar with media key controls
  - Background grid lines for depth
"""
import math
import threading
import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QPen, QColor, QFont, QFontMetrics,
    QLinearGradient, QRadialGradient, QPainterPath, QBrush
)
from ui.design_tokens import C, SP, FONT, FONT_MONO, PAINTER


class WaveformHeroPanel(QWidget):
    """
    Full-width waveform visualization with overlaid info.
    Captures system audio via WASAPI loopback for real-time display.
    """
    # Signals for thread-safe updates
    _audio_ready = Signal()
    record_clicked = Signal()    # emitted when Record button is pressed
    autotune_toggled = Signal(bool)  # emitted when Auto-Tune pill is toggled

    GRID_LINES_H = 6
    GRID_LINES_V = 20
    WAVEFORM_POINTS = 256    # render resolution
    REFLECT_ALPHA = 0.18     # mirror reflection opacity

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(160)

        # State
        self._song_title = ""
        self._key_display = "C"
        self._scale_display = "Major"
        self._bpm = 0
        self._midi_connected = False
        self._autotune_on = False
        self._score = 0
        self._recording = False
        self._rec_pulse = 0.0   # 0..1 pulsing alpha for record dot
        self._audio_buffer = np.zeros(self.WAVEFORM_POINTS, dtype=np.float32)
        self._capture_thread = None
        self._capture_running = False
        self._phase = 0.0  # animated fallback phase

        # Animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30fps

        self._audio_ready.connect(self.update)

        # Start audio capture
        self._start_audio_capture()

    # ── Public API ───────────────────────────────────────────
    def set_song_info(self, title="", key="C", scale="Major", bpm=0):
        self._song_title = title
        self._key_display = key
        self._scale_display = scale
        self._bpm = bpm
        self.update()

    def set_midi_status(self, connected):
        self._midi_connected = connected
        self.update()

    def set_autotune(self, on):
        self._autotune_on = on
        self.update()

    def set_score(self, score):
        self._score = score
        self.update()

    def set_recording(self, recording: bool):
        self._recording = recording
        self.update()

    def stop(self):
        self._capture_running = False
        self._timer.stop()

    # ── Audio Capture ────────────────────────────────────────
    def _start_audio_capture(self):
        """Start lightweight WASAPI loopback capture for waveform."""
        self._capture_running = True
        self._capture_thread = threading.Thread(
            target=self._capture_loop, daemon=True
        )
        self._capture_thread.start()

    def _capture_loop(self):
        """Background thread: capture system audio via WASAPI loopback."""
        try:
            import pyaudiowpatch as paw
            pa = paw.PyAudio()

            # Find default loopback device
            wasapi_info = None
            for i in range(pa.get_host_api_count()):
                api = pa.get_host_api_info_by_index(i)
                if api.get("name", "").startswith("Windows WASAPI"):
                    wasapi_info = api
                    break

            if not wasapi_info:
                pa.terminate()
                return

            default_speakers = pa.get_device_info_by_index(
                wasapi_info["defaultOutputDevice"]
            )

            # Look for loopback variant
            loopback_dev = None
            for i in range(pa.get_device_count()):
                dev = pa.get_device_info_by_index(i)
                if (dev.get("isLoopbackDevice", False) and
                    dev["name"].startswith(default_speakers["name"][:20])):
                    loopback_dev = dev
                    break

            if not loopback_dev:
                # Fallback: use default speakers directly
                loopback_dev = default_speakers

            channels = int(loopback_dev.get("maxInputChannels", 2))
            if channels < 1:
                channels = 2
            rate = int(loopback_dev.get("defaultSampleRate", 44100))
            chunk = self.WAVEFORM_POINTS * 2

            stream = pa.open(
                format=paw.paFloat32,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=int(loopback_dev["index"]),
                frames_per_buffer=chunk,
            )

            while self._capture_running:
                try:
                    data = stream.read(chunk, exception_on_overflow=False)
                    samples = np.frombuffer(data, dtype=np.float32)
                    # Downmix to mono
                    if channels > 1:
                        samples = samples.reshape(-1, channels).mean(axis=1)
                    # Downsample to WAVEFORM_POINTS
                    if len(samples) >= self.WAVEFORM_POINTS:
                        step = len(samples) // self.WAVEFORM_POINTS
                        self._audio_buffer = samples[::step][:self.WAVEFORM_POINTS]
                    else:
                        self._audio_buffer[:len(samples)] = samples
                    self._audio_ready.emit()
                except Exception:
                    break

            stream.stop_stream()
            stream.close()
            pa.terminate()
        except Exception as e:
            print(f"⚠️ [WAVEFORM] Audio capture failed: {e}")

    def _tick(self):
        self._phase += 0.05
        # Animate record pulse
        if self._recording:
            self._rec_pulse = (self._rec_pulse + 0.08) % (2 * 3.14159)
        self.update()

    # ── Paint ────────────────────────────────────────────────
    def paintEvent(self, _):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        rect = QRectF(0, 0, w, h)

        # ── Background ───────────────────────────────────────
        self._paint_background(p, w, h)

        # ── Grid lines ───────────────────────────────────────
        self._paint_grid(p, w, h)

        # ── Waveform + reflection ────────────────────────────
        wave_top = h * 0.15
        wave_h = h * 0.45
        reflect_h = h * 0.25
        self._paint_waveform(p, w, wave_top, wave_h, reflect_h)

        # ── Overlays ─────────────────────────────────────────
        self._paint_song_info(p, w, h)
        self._paint_status_badges(p, w, h)
        self._paint_transport(p, w, h)

        p.end()

    def _paint_background(self, p, w, h):
        """Dark background with subtle radial glow."""
        p.setPen(Qt.NoPen)
        # Base
        _wb_top = QColor(C["card"]); _wb_top.setAlpha(235)
        _wb_mid = QColor(C["bg"]);   _wb_mid.setAlpha(250)
        _wb_bot = QColor(C["bg"]);   _wb_bot.setAlpha(255)
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, _wb_top)
        bg_grad.setColorAt(0.5, _wb_mid)
        bg_grad.setColorAt(1.0, _wb_bot)
        p.setBrush(bg_grad)
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)

        # Center radial glow — gold (primary) + kim cương (creative).
        _g0 = QColor(C["primary"]);  _g0.setAlpha(12)
        _g1 = QColor(C["creative"]); _g1.setAlpha(6)
        glow = QRadialGradient(w / 2, h * 0.4, w * 0.5)
        glow.setColorAt(0, _g0)
        glow.setColorAt(0.6, _g1)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setBrush(glow)
        p.drawRoundedRect(QRectF(0, 0, w, h), 12, 12)

        # Border
        border_grad = QLinearGradient(0, 0, w, h)
        border_grad.setColorAt(0, QColor(56, 189, 248, 30))
        border_grad.setColorAt(0.5, QColor(168, 85, 247, 20))
        border_grad.setColorAt(1, QColor(236, 72, 153, 15))
        p.setPen(QPen(QBrush(border_grad), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 12, 12)

    def _paint_grid(self, p, w, h):
        """Subtle grid lines for depth."""
        grid_pen = QPen(QColor(56, 189, 248, 10), 0.5)
        p.setPen(grid_pen)
        # Horizontal
        for i in range(1, self.GRID_LINES_H):
            y = h * i / self.GRID_LINES_H
            p.drawLine(QPointF(20, y), QPointF(w - 20, y))
        # Vertical
        for i in range(1, self.GRID_LINES_V):
            x = w * i / self.GRID_LINES_V
            p.drawLine(QPointF(x, h * 0.1), QPointF(x, h * 0.85))

    def _paint_waveform(self, p, w, top, wave_h, reflect_h):
        """Wavebar style — mỗi cột là thanh đứng đối xứng từ tâm."""
        n = self.WAVEFORM_POINTS
        buf = self._audio_buffer
        margin = 24
        usable_w = w - margin * 2

        # Bar sizing — số bar cố định, khoảng cách đều nhau
        BAR_COUNT = 64
        bar_gap = 2
        bar_w = max(2.0, (usable_w - bar_gap * (BAR_COUNT - 1)) / BAR_COUNT)
        step = n / BAR_COUNT

        center_y = top + wave_h / 2
        has_audio = np.max(np.abs(buf)) > 0.001

        # Gradient ngang cho toàn bộ khu vực
        wave_grad = QLinearGradient(margin, 0, w - margin, 0)
        wave_grad.setColorAt(0.0,  QColor(PAINTER["waveform_grad_1"]))
        wave_grad.setColorAt(0.45, QColor(PAINTER["waveform_grad_2"]))
        wave_grad.setColorAt(1.0,  QColor(PAINTER["waveform_grad_3"]))

        p.setPen(Qt.NoPen)

        for i in range(BAR_COUNT):
            # Lấy amp
            if has_audio:
                idx = int(i * step)
                amp = float(np.abs(buf[idx])) if idx < len(buf) else 0.0
                amp = min(1.0, amp * 1.6)           # boost nhẹ
            else:
                # Idle: sóng sine nhiều tầng + hình bao Gaussian
                t = i / (BAR_COUNT - 1)
                envelope = math.sin(math.pi * t)    # fade in/out 2 đầu
                amp = envelope * max(0.0, (
                    0.35 * math.sin(self._phase * 1.0 + i * 0.22) +
                    0.20 * math.sin(self._phase * 1.7 + i * 0.40) +
                    0.10 * math.sin(self._phase * 2.7 + i * 0.65)
                ))
                amp = abs(amp)

            amp = max(0.0, min(1.0, amp))

            bar_h_half = max(2.0, amp * (wave_h / 2) * 0.88)
            x = margin + i * (bar_w + bar_gap)

            # ─── Thanh chính (trên + dưới đối xứng) ───────────
            # Màu theo amplitude: mờ khi yên lặng, sáng khi to
            alpha = int(80 + amp * 170)
            # Màu gradient dựa vào vị trí ngang (lấy qua QLinearGradient)
            t = i / (BAR_COUNT - 1)
            r1, g1, b1 = 56, 189, 248   # teal
            r2, g2, b2 = 168, 85, 247   # purple
            r3, g3, b3 = 236, 72, 153   # pink
            if t < 0.5:
                tt = t * 2
                r = int(r1 + (r2 - r1) * tt)
                g = int(g1 + (g2 - g1) * tt)
                b = int(b1 + (b2 - b1) * tt)
            else:
                tt = (t - 0.5) * 2
                r = int(r2 + (r3 - r2) * tt)
                g = int(g2 + (g3 - g2) * tt)
                b = int(b2 + (b3 - b2) * tt)

            color = QColor(r, g, b, alpha)

            # Mỗi thanh: gradient dọc (sáng ở giữa)
            bar_grad = QLinearGradient(x, center_y - bar_h_half,
                                       x, center_y + bar_h_half)
            top_c = QColor(r, g, b, alpha)
            mid_c = QColor(min(255, r + 60), min(255, g + 60), min(255, b + 60), alpha)
            bot_c = QColor(r, g, b, int(alpha * 0.6))
            bar_grad.setColorAt(0.0, top_c)
            bar_grad.setColorAt(0.5, mid_c)
            bar_grad.setColorAt(1.0, bot_c)

            p.setBrush(bar_grad)
            radius = min(bar_w / 2, 2.5)
            p.drawRoundedRect(
                QRectF(x, center_y - bar_h_half, bar_w, bar_h_half * 2),
                radius, radius
            )

            # ─── Phản chiếu (mờ dần xuống dưới) ───────────────
            if amp > 0.05:
                ref_h = bar_h_half * self.REFLECT_ALPHA * 0.8
                ref_grad = QLinearGradient(x, center_y + bar_h_half,
                                           x, center_y + bar_h_half + ref_h)
                ref_c1 = QColor(r, g, b, int(alpha * 0.28))
                ref_c2 = QColor(r, g, b, 0)
                ref_grad.setColorAt(0.0, ref_c1)
                ref_grad.setColorAt(1.0, ref_c2)
                p.setBrush(ref_grad)
                p.drawRoundedRect(
                    QRectF(x, center_y + bar_h_half, bar_w, ref_h),
                    radius, radius
                )

        # ─── Center line (baseline guide) ──────────────────────
        p.setPen(QPen(QColor(56, 189, 248, 18), 1))
        p.drawLine(QPointF(margin, center_y), QPointF(w - margin, center_y))


    def _paint_song_info(self, p, w, h):
        """Top-left overlay: song title, key badge, BPM."""
        x, y = 20, 16

        # Song title
        if self._song_title:
            font = QFont()
            font.setFamily("Segoe UI")
            font.setPixelSize(18)
            font.setBold(True)
            p.setFont(font)

            # Glow
            p.setPen(QColor(252, 132, 3, 40))
            p.drawText(x + 1, y + 19, self._song_title[:50])
            # Text
            p.setPen(QColor(252, 132, 3))
            p.drawText(x, y + 18, self._song_title[:50])

            y += 28

        # Key badge
        key_text = f"{self._key_display} {self._scale_display}"
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPixelSize(12)
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(key_text) + 16

        # Badge background
        badge_rect = QRectF(x, y, tw, 22)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(56, 189, 248, 30))
        p.drawRoundedRect(badge_rect, 6, 6)
        p.setPen(QPen(QColor(56, 189, 248, 80), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(badge_rect, 6, 6)
        p.setPen(QColor(56, 189, 248))
        p.drawText(badge_rect, Qt.AlignCenter, key_text)

        # BPM
        if self._bpm > 0:
            bpm_x = x + tw + 8
            bpm_text = f"{self._bpm} BPM"
            bpm_w = fm.horizontalAdvance(bpm_text) + 16
            bpm_rect = QRectF(bpm_x, y, bpm_w, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(168, 85, 247, 25))
            p.drawRoundedRect(bpm_rect, 6, 6)
            p.setPen(QColor(168, 85, 247, 180))
            p.drawText(bpm_rect, Qt.AlignCenter, bpm_text)

    def _paint_status_badges(self, p, w, h):
        """Top-right: MIDI ring, Auto-Tune pill, Score ring."""
        rx = w - 20

        # ── Score ring (rightmost) ───────────────────────────
        if self._score > 0:
            ring_r = 22
            ring_cx = rx - ring_r
            ring_cy = 30
            self._draw_score_ring(p, ring_cx, ring_cy, ring_r, self._score)
            rx = ring_cx - ring_r - 12

        # ── Auto-Tune pill ───────────────────────────────────
        pill_w, pill_h = 78, 24
        pill_x = rx - pill_w
        pill_y = 16
        self._draw_autotune_pill(p, pill_x, pill_y, pill_w, pill_h)
        rx = pill_x - 12

        # ── MIDI status ring ─────────────────────────────────
        midi_r = 8
        midi_cx = rx - midi_r
        midi_cy = 28
        color = QColor(C["teal"]) if self._midi_connected else QColor(C["accent"])
        # Glow
        glow = QRadialGradient(midi_cx, midi_cy, midi_r * 3)
        gc = QColor(color)
        gc.setAlpha(40 if self._midi_connected else 15)
        glow.setColorAt(0, gc)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(midi_cx - midi_r * 3, midi_cy - midi_r * 3,
                              midi_r * 6, midi_r * 6))
        # Ring
        p.setPen(QPen(color, 2))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(midi_cx - midi_r, midi_cy - midi_r,
                              midi_r * 2, midi_r * 2))
        # Center dot
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QRectF(midi_cx - 3, midi_cy - 3, 6, 6))

    def _draw_score_ring(self, p, cx, cy, r, score):
        """Mini score ring."""
        # Background arc
        arc_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.setPen(QPen(QColor(50, 60, 80, 100), 3))
        p.setBrush(Qt.NoBrush)
        p.drawArc(arc_rect, 90 * 16, -360 * 16)

        # Score arc
        span = int((score / 100.0) * 360)
        score_color = QColor(C["green"]) if score >= 80 else (
            QColor(C["orange"]) if score >= 60 else QColor(C["accent"]))
        p.setPen(QPen(score_color, 3, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc_rect, 90 * 16, -span * 16)

        # Center text
        font = QFont()
        font.setFamily("Consolas")
        font.setPixelSize(12)
        font.setBold(True)
        p.setFont(font)
        p.setPen(score_color)
        p.drawText(arc_rect, Qt.AlignCenter, str(int(score)))

    def _draw_autotune_pill(self, p, x, y, w, h):
        """Auto-Tune ON/OFF pill toggle."""
        rect = QRectF(x, y, w, h)
        r = h / 2

        if self._autotune_on:
            # ON state
            bg_grad = QLinearGradient(x, y, x + w, y)
            bg_grad.setColorAt(0, QColor(16, 185, 129, 180))
            bg_grad.setColorAt(1, QColor(56, 189, 248, 150))
            p.setPen(QPen(QColor(16, 185, 129, 120), 1))
            p.setBrush(bg_grad)
        else:
            p.setPen(QPen(QColor(100, 116, 139, 80), 1))
            p.setBrush(QColor(30, 41, 59, 150))

        p.drawRoundedRect(rect, r, r)

        # Text
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        text = "AT ON" if self._autotune_on else "AT OFF"
        tc = QColor("#FFFFFF") if self._autotune_on else QColor(C["text_muted"])
        p.setPen(tc)
        p.drawText(rect, Qt.AlignCenter, text)

    def _paint_transport(self, p, w, h):
        """Bottom transport bar: [prev][play][next] | [● Record] | [──●── time]"""
        import math
        bar_h = 36
        bar_y = h - bar_h - 8
        bar_margin = 20
        bar_w = w - bar_margin * 2
        bar_rect = QRectF(bar_margin, bar_y, bar_w, bar_h)
        bar_cy = bar_y + bar_h / 2

        # Background
        _pb = QColor(C["bg"]); _pb.setAlpha(200)
        p.setPen(Qt.NoPen)
        p.setBrush(_pb)
        p.drawRoundedRect(bar_rect, bar_h / 2, bar_h / 2)

        # Border
        _pbd = QColor(C["primary"]); _pbd.setAlpha(30)
        p.setPen(QPen(_pbd, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(bar_rect, bar_h / 2, bar_h / 2)

        # ── LEFT: Transport buttons ⏮ ⏯ ⏭ ──────────────────
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPixelSize(15)
        p.setFont(font)

        left_x = bar_margin + 20
        transport_btns = [("⏮", left_x), ("⏯", left_x + 32), ("⏭", left_x + 64)]
        for text, bx in transport_btns:
            p.setPen(QColor(148, 163, 184))
            p.drawText(QRectF(bx - 12, bar_y, 24, bar_h), Qt.AlignCenter, text)

        # ── CENTER: Record button ─────────────────────────────
        rec_cx = bar_margin + bar_w / 2
        rec_cy = bar_cy
        rec_r = 13

        if self._recording:
            # Pulsing glow
            pulse = 0.5 + 0.5 * math.sin(self._rec_pulse)
            glow_r = rec_r + 6 + pulse * 4
            glow = QColor(239, 68, 68, int(40 * pulse))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QRectF(rec_cx - glow_r, rec_cy - glow_r,
                                  glow_r * 2, glow_r * 2))

        # Record pill background
        pill_w, pill_h2 = 90, 26
        pill_x = rec_cx - pill_w / 2
        pill_y = rec_cy - pill_h2 / 2
        pill_rect = QRectF(pill_x, pill_y, pill_w, pill_h2)

        if self._recording:
            rec_bg = QLinearGradient(pill_x, pill_y, pill_x + pill_w, pill_y)
            rec_bg.setColorAt(0, QColor(239, 68, 68, 220))
            rec_bg.setColorAt(1, QColor(185, 28, 28, 200))
            p.setPen(QPen(QColor(239, 68, 68, 180), 1.5))
            p.setBrush(rec_bg)
        else:
            p.setPen(QPen(QColor(239, 68, 68, 120), 1.5))
            p.setBrush(QColor(30, 15, 15, 180))
        p.drawRoundedRect(pill_rect, pill_h2 / 2, pill_h2 / 2)

        # Record dot + text
        dot_r = 4
        dot_x = pill_x + 16
        p.setPen(Qt.NoPen)
        dot_color = QColor(255, 255, 255) if self._recording else QColor(239, 68, 68)
        p.setBrush(dot_color)
        p.drawEllipse(QRectF(dot_x - dot_r, rec_cy - dot_r, dot_r * 2, dot_r * 2))

        font2 = QFont()
        font2.setFamily("Segoe UI")
        font2.setPixelSize(11)
        font2.setBold(True)
        p.setFont(font2)
        text_color = QColor(255, 255, 255) if self._recording else QColor(239, 68, 68)
        p.setPen(text_color)
        label = "REC" if self._recording else "RECORD"
        p.drawText(QRectF(dot_x + dot_r + 4, pill_y, pill_w - 28, pill_h2), Qt.AlignVCenter, label)

        # ── RIGHT: Timeline progress ──────────────────────────
        tl_x = rec_cx + pill_w / 2 + 16
        tl_w = bar_w - (tl_x - bar_margin) - 16
        tl_cy = bar_cy
        tl_h = 3

        if tl_w > 60:
            # Track
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(51, 65, 85, 120))
            p.drawRoundedRect(QRectF(tl_x, tl_cy - tl_h / 2, tl_w, tl_h), 2, 2)

            # Progress (static idle)
            progress = 0.35
            prog_grad = QLinearGradient(tl_x, 0, tl_x + tl_w * progress, 0)
            prog_grad.setColorAt(0, QColor(56, 189, 248, 180))
            prog_grad.setColorAt(1, QColor(168, 85, 247, 160))
            p.setBrush(prog_grad)
            p.drawRoundedRect(QRectF(tl_x, tl_cy - tl_h / 2,
                                      tl_w * progress, tl_h), 2, 2)

            # Thumb
            thumb_x = tl_x + tl_w * progress
            p.setBrush(QColor(226, 232, 240))
            p.drawEllipse(QRectF(thumb_x - 5, tl_cy - 5, 10, 10))

            # Time text
            font3 = QFont()
            font3.setFamily("Consolas")
            font3.setPixelSize(10)
            p.setFont(font3)
            p.setPen(QColor(100, 116, 139))
            time_rect = QRectF(tl_x, bar_y, tl_w, bar_h)
            p.drawText(time_rect, Qt.AlignRight | Qt.AlignVCenter, "2:34 / 4:12")

    # ── Mouse events for transport ───────────────────────────
    def mousePressEvent(self, e):
        """Handle clicks on transport buttons, Record pill, and Auto-Tune."""
        x, y = e.position().x(), e.position().y()
        w, h = self.width(), self.height()

        bar_h = 36
        bar_y = h - bar_h - 8
        bar_margin = 20
        bar_w = w - bar_margin * 2

        if bar_y <= y <= bar_y + bar_h:
            bar_cx = bar_margin + bar_w / 2
            bar_cy = bar_y + bar_h / 2

            # Transport left buttons
            left_x = bar_margin + 20
            if abs(x - left_x) < 16:
                self._send_media_key("prev")
                return
            elif abs(x - (left_x + 32)) < 16:
                self._send_media_key("play_pause")
                return
            elif abs(x - (left_x + 64)) < 16:
                self._send_media_key("next")
                return

            # Record pill
            pill_w, pill_h2 = 90, 26
            pill_x = bar_cx - pill_w / 2
            pill_y2 = bar_cy - pill_h2 / 2
            if pill_x <= x <= pill_x + pill_w and pill_y2 <= y <= pill_y2 + pill_h2:
                self._recording = not self._recording
                self.update()
                self.record_clicked.emit()
                return

        # Auto-Tune pill area (top-right)
        pill_w, pill_h = 78, 24
        rx = w - 20
        if self._score > 0:
            rx -= 56
        pill_x = rx - pill_w
        pill_y = 16
        if pill_x <= x <= pill_x + pill_w and pill_y <= y <= pill_y + pill_h:
            self._autotune_on = not self._autotune_on
            self.autotune_toggled.emit(self._autotune_on)
            self.update()

    def _send_media_key(self, action):
        """Send Windows media key to control YouTube in browser."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            VK_MAP = {
                "play_pause": 0xB3,
                "next": 0xB0,
                "prev": 0xB1,
            }
            vk = VK_MAP.get(action)
            if vk:
                user32.keybd_event(vk, 0, 0, 0)       # key down
                user32.keybd_event(vk, 0, 0x0002, 0)   # key up
        except Exception as e:
            print(f"⚠️ [TRANSPORT] Media key failed: {e}")
