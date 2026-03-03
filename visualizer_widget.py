"""
Waveform Visualizer Widget — Custom QPainter-based widget for rendering
animated waveforms with gradient colors, glow effects, and mirror reflections.
"""

import numpy as np
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, QPointF
from PyQt5.QtGui import (
    QPainter, QPainterPath, QLinearGradient, QRadialGradient,
    QColor, QPen, QFont, QBrush
)


# Color themes: each has (primary_hue, secondary_hue, accent_hue)
COLOR_THEMES = {
    "Neon Cyan": {
        "primary": QColor(0, 255, 255),
        "secondary": QColor(0, 150, 255),
        "accent": QColor(255, 0, 200),
        "bg_top": QColor(10, 10, 30),
        "bg_bottom": QColor(5, 5, 20),
        "grid": QColor(30, 30, 60),
    },
    "Sunset": {
        "primary": QColor(255, 100, 50),
        "secondary": QColor(255, 180, 0),
        "accent": QColor(255, 50, 100),
        "bg_top": QColor(30, 10, 15),
        "bg_bottom": QColor(15, 5, 10),
        "grid": QColor(50, 20, 30),
    },
    "Emerald": {
        "primary": QColor(0, 255, 140),
        "secondary": QColor(0, 200, 100),
        "accent": QColor(100, 255, 200),
        "bg_top": QColor(5, 20, 15),
        "bg_bottom": QColor(2, 10, 8),
        "grid": QColor(15, 40, 30),
    },
    "Purple Rain": {
        "primary": QColor(180, 80, 255),
        "secondary": QColor(100, 50, 255),
        "accent": QColor(255, 100, 255),
        "bg_top": QColor(15, 5, 30),
        "bg_bottom": QColor(8, 2, 15),
        "grid": QColor(30, 15, 50),
    },
    "Monochrome": {
        "primary": QColor(220, 220, 220),
        "secondary": QColor(150, 150, 150),
        "accent": QColor(255, 255, 255),
        "bg_top": QColor(15, 15, 15),
        "bg_bottom": QColor(5, 5, 5),
        "grid": QColor(35, 35, 35),
    },
}


class WaveformWidget(QWidget):
    """Custom widget that renders an animated waveform with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 300)

        # Waveform data
        self._waveform = np.zeros(800, dtype=np.float32)
        self._rms = 0.0
        self._spectral_centroid = 0.5
        self._zcr = 0.0

        # Visual settings
        self._theme_name = "Neon Cyan"
        self._theme = COLOR_THEMES[self._theme_name]
        self._show_mirror = True
        self._show_glow = True
        self._show_grid = True
        self._show_fill = True

        # FPS tracking
        self._frame_count = 0
        self._fps = 0
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(1000)

        # Animation timer (target ~30 FPS for the idle animation)
        self._idle_phase = 0.0
        self._idle_timer = QTimer(self)
        self._idle_timer.timeout.connect(self._idle_tick)
        self._idle_timer.start(33)

        self._is_active = False

    def set_theme(self, theme_name):
        """Switch color theme."""
        if theme_name in COLOR_THEMES:
            self._theme_name = theme_name
            self._theme = COLOR_THEMES[theme_name]
            self.update()

    def set_mirror(self, enabled):
        self._show_mirror = enabled
        self.update()

    def set_glow(self, enabled):
        self._show_glow = enabled
        self.update()

    def update_data(self, waveform, rms, spectral_centroid, zcr):
        """Update the waveform data from the audio processor."""
        self._waveform = waveform
        self._rms = rms
        self._spectral_centroid = spectral_centroid
        self._zcr = zcr
        self._is_active = True
        self.update()

    def clear_data(self):
        """Reset to idle state."""
        self._waveform = np.zeros(800, dtype=np.float32)
        self._rms = 0.0
        self._is_active = False
        self.update()

    def _idle_tick(self):
        """Animate idle state with subtle wave."""
        self._idle_phase += 0.05
        if not self._is_active:
            self.update()

    def _update_fps(self):
        self._fps = self._frame_count
        self._frame_count = 0

    def paintEvent(self, event):
        self._frame_count += 1
        w = self.width()
        h = self.height()
        center_y = h / 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        # --- Background gradient ---
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0, self._theme["bg_top"])
        bg_grad.setColorAt(1, self._theme["bg_bottom"])
        painter.fillRect(0, 0, w, h, bg_grad)

        # --- Grid lines ---
        if self._show_grid:
            grid_pen = QPen(self._theme["grid"], 1, Qt.DotLine)
            painter.setPen(grid_pen)
            # Horizontal lines
            for i in range(1, 6):
                y = h * i / 6
                painter.drawLine(0, int(y), w, int(y))
            # Vertical lines
            for i in range(1, 12):
                x = w * i / 12
                painter.drawLine(int(x), 0, int(x), h)

        # --- Build waveform path ---
        waveform = self._waveform
        n = len(waveform)

        if n < 2:
            painter.end()
            return

        # Add idle wave if not active
        if not self._is_active or self._rms < 0.01:
            idle_wave = np.sin(
                np.linspace(0, 4 * np.pi, n) + self._idle_phase
            ) * 0.03
            waveform = idle_wave.astype(np.float32)

        # Scale waveform to pixel coordinates
        amplitude = h * 0.35  # Max amplitude in pixels
        x_step = w / (n - 1)

        # Build upper waveform path
        path = QPainterPath()
        points = []
        for i in range(n):
            x = i * x_step
            y = center_y - waveform[i] * amplitude
            points.append(QPointF(x, y))

        if points:
            path.moveTo(points[0])
            # Use quadratic bezier for smooth curves
            for i in range(1, len(points) - 1, 2):
                if i + 1 < len(points):
                    path.quadTo(points[i], points[i + 1])
                else:
                    path.lineTo(points[i])

        # --- Glow effect (draw wider, semi-transparent line behind) ---
        if self._show_glow and self._rms > 0.01:
            glow_color = QColor(self._theme["primary"])
            glow_intensity = min(80, int(self._rms * 160))
            glow_color.setAlpha(glow_intensity)
            glow_pen = QPen(glow_color, 8 + self._rms * 10)
            glow_pen.setCapStyle(Qt.RoundCap)
            glow_pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(glow_pen)
            painter.drawPath(path)

            # Second, tighter glow layer
            glow_color2 = QColor(self._theme["secondary"])
            glow_color2.setAlpha(glow_intensity + 20)
            glow_pen2 = QPen(glow_color2, 4 + self._rms * 5)
            glow_pen2.setCapStyle(Qt.RoundCap)
            glow_pen2.setJoinStyle(Qt.RoundJoin)
            painter.setPen(glow_pen2)
            painter.drawPath(path)

        # --- Fill under waveform ---
        if self._show_fill:
            fill_path = QPainterPath(path)
            fill_path.lineTo(w, center_y)
            fill_path.lineTo(0, center_y)
            fill_path.closeSubpath()

            fill_grad = QLinearGradient(0, center_y - amplitude, 0, center_y)
            fill_color = QColor(self._theme["primary"])
            fill_color.setAlpha(int(30 + self._rms * 60))
            fill_grad.setColorAt(0, fill_color)
            fill_color_transparent = QColor(self._theme["primary"])
            fill_color_transparent.setAlpha(5)
            fill_grad.setColorAt(1, fill_color_transparent)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(fill_grad))
            painter.drawPath(fill_path)

        # --- Main waveform line ---
        line_grad = QLinearGradient(0, 0, w, 0)
        # Color shifts based on spectral centroid
        sc = self._spectral_centroid
        primary = self._theme["primary"]
        secondary = self._theme["secondary"]
        accent = self._theme["accent"]

        line_grad.setColorAt(0.0, self._blend_color(secondary, primary, sc))
        line_grad.setColorAt(0.5, primary)
        line_grad.setColorAt(1.0, self._blend_color(primary, accent, sc))

        main_pen = QPen(QBrush(line_grad), 2.0 + self._rms * 2.0)
        main_pen.setCapStyle(Qt.RoundCap)
        main_pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(main_pen)
        painter.drawPath(path)

        # --- Mirror (reflection below center) ---
        if self._show_mirror:
            mirror_path = QPainterPath()
            mirror_points = []
            for i in range(n):
                x = i * x_step
                y = center_y + waveform[i] * amplitude * 0.5
                mirror_points.append(QPointF(x, y))

            if mirror_points:
                mirror_path.moveTo(mirror_points[0])
                for i in range(1, len(mirror_points) - 1, 2):
                    if i + 1 < len(mirror_points):
                        mirror_path.quadTo(mirror_points[i], mirror_points[i + 1])
                    else:
                        mirror_path.lineTo(mirror_points[i])

            # Mirror fill
            mirror_fill = QPainterPath(mirror_path)
            mirror_fill.lineTo(w, center_y)
            mirror_fill.lineTo(0, center_y)
            mirror_fill.closeSubpath()

            mfill_grad = QLinearGradient(0, center_y, 0, center_y + amplitude * 0.5)
            mfill_color = QColor(self._theme["primary"])
            mfill_color.setAlpha(10)
            mfill_grad.setColorAt(0, mfill_color)
            mfill_transparent = QColor(self._theme["primary"])
            mfill_transparent.setAlpha(0)
            mfill_grad.setColorAt(1, mfill_transparent)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(mfill_grad))
            painter.drawPath(mirror_fill)

            # Mirror line
            mirror_color = QColor(self._theme["primary"])
            mirror_color.setAlpha(60)
            mirror_pen = QPen(mirror_color, 1.0 + self._rms * 0.5)
            mirror_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(mirror_pen)
            painter.drawPath(mirror_path)

        # --- Center line ---
        center_pen = QPen(QColor(self._theme["grid"]), 1, Qt.SolidLine)
        painter.setPen(center_pen)
        painter.drawLine(0, int(center_y), w, int(center_y))

        # --- FPS & info overlay ---
        painter.setPen(QColor(100, 100, 100))
        font = QFont("Consolas", 9)
        painter.setFont(font)
        painter.drawText(10, 20, f"FPS: {self._fps}")
        painter.drawText(10, 35, f"RMS: {self._rms:.3f}")

        # --- Status label ---
        if not self._is_active:
            painter.setPen(QColor(80, 80, 80))
            status_font = QFont("Segoe UI", 14)
            painter.setFont(status_font)
            painter.drawText(
                self.rect(), Qt.AlignCenter,
                "♪  Waiting for audio...  ♪"
            )

        painter.end()

    @staticmethod
    def _blend_color(c1, c2, t):
        """Blend two QColors by factor t (0=c1, 1=c2)."""
        t = max(0.0, min(1.0, t))
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
        )

    @staticmethod
    def get_theme_names():
        return list(COLOR_THEMES.keys())
