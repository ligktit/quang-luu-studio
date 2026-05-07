"""
core.accessibility.announcer
============================
Cầu nối giữa state changes của app → Speaker (TTS).

Hai loại event:
1. Focus events  → đọc accessibleName + accessibleDescription của widget mới.
2. State events  → câu thông báo cố định (MIDI connect, tone detected, score...).

Slider value change được debounce 300ms để tránh spam khi kéo fader.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication, QAbstractSlider, QPushButton, QComboBox, QLabel

from .speaker import Speaker

log = logging.getLogger("accessibility.announcer")


# Map value text shown bên cạnh fader (đã có) → câu nói gọn.
_KEY_VN = {
    "C": "Đô", "C#": "Đô thăng", "Db": "Rê giáng",
    "D": "Rê", "D#": "Rê thăng", "Eb": "Mi giáng",
    "E": "Mi", "F": "Fa", "F#": "Fa thăng", "Gb": "Sol giáng",
    "G": "Sol", "G#": "Sol thăng", "Ab": "La giáng",
    "A": "La", "A#": "La thăng", "Bb": "Si giáng",
    "B": "Si",
}

_SCALE_VN = {"Major": "trưởng", "Minor": "thứ"}


def key_to_vn(key: str, scale: str = "") -> str:
    base = _KEY_VN.get((key or "").strip(), key)
    if scale:
        return f"{base} {_SCALE_VN.get(scale, scale)}"
    return base


class _SliderDebouncer:
    """Debounce 300ms cho mỗi slider key (vd: 'mix_music')."""

    def __init__(self, parent_obj, callback, delay_ms: int = 300):
        self._timers: dict = {}
        self._values: dict = {}
        self._parent = parent_obj
        self._callback = callback
        self._delay = int(delay_ms)

    def push(self, key: str, value):
        self._values[key] = value
        timer = self._timers.get(key)
        if timer is None:
            timer = QTimer(self._parent)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda k=key: self._fire(k))
            self._timers[key] = timer
        timer.start(self._delay)

    def _fire(self, key: str):
        val = self._values.pop(key, None)
        if val is None:
            return
        try:
            self._callback(key, val)
        except Exception as e:
            log.debug("Slider debouncer callback error: %s", e)


class Announcer(QObject):
    """
    Service đọc nội dung qua TTS theo các event của app.

    Cách dùng:
        announcer = Announcer(speaker, dashboard)
        announcer.attach_focus_filter()           # bắt focus events toàn app
        announcer.hook_dashboard_signals()        # bắt MIDI/tone/score signals
        # ... khi có state change tự gọi:
        announcer.announce_state("Đã lưu bài hát")
    """

    def __init__(self, speaker: Speaker, dashboard, *, announce_focus: bool = True,
                 announce_state: bool = True):
        super().__init__(dashboard)
        self._speaker = speaker
        self._dashboard = dashboard
        self._announce_focus = bool(announce_focus)
        self._announce_state = bool(announce_state)
        self._last_announced_widget = None

        self._slider_debouncer = _SliderDebouncer(
            dashboard,
            self._on_slider_settled,
            delay_ms=300,
        )

        # Cache nhãn cho slider keys (gán ở hook_dashboard_signals)
        self._slider_label_map = {
            "mix_music":  "Nhạc",
            "mix_mic":    "Mic",
            "mix_reverb": "Vang",
            "tone_music": "Giọng",
        }

    # ── Settings ────────────────────────────────────────────

    def set_announce_focus(self, value: bool):
        self._announce_focus = bool(value)

    def set_announce_state(self, value: bool):
        self._announce_state = bool(value)

    # ── Public state announcements ──────────────────────────

    def announce_state(self, text: str, priority: str = "normal"):
        if self._announce_state and self._speaker is not None:
            self._speaker.speak(text, priority=priority)

    def announce_error(self, text: str):
        # Lỗi luôn được đọc kể cả khi tắt announce_state? — vẫn theo cờ để
        # user có thể tắt hoàn toàn nếu muốn dùng NVDA.
        if self._speaker is not None:
            self._speaker.speak(text, priority="high")

    # ── Focus event filter ──────────────────────────────────

    def attach_focus_filter(self):
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def detach_focus_filter(self):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802 — Qt API name
        if event.type() == QEvent.FocusIn and self._announce_focus:
            self._on_widget_focused(obj)
        return False  # không nuốt event

    def _on_widget_focused(self, w):
        if w is None or w is self._last_announced_widget:
            return
        self._last_announced_widget = w
        try:
            name = w.accessibleName() if hasattr(w, "accessibleName") else ""
            desc = w.accessibleDescription() if hasattr(w, "accessibleDescription") else ""
        except Exception:
            return
        text = ""
        # Combobox: đọc tên + giá trị hiện tại
        if isinstance(w, QComboBox):
            text = f"{name or 'Lựa chọn'}: {w.currentText()}"
        elif isinstance(w, QPushButton):
            label = name or w.text() or "Nút"
            text = label
        elif isinstance(w, QAbstractSlider):
            text = f"{name or 'Thanh trượt'}: {w.value()}"
        elif name:
            text = name
        if desc and text:
            text = f"{text}. {desc}"
        if text:
            self.announce_state(text)

    # ── Slider value debounce ───────────────────────────────

    def announce_slider(self, slider_key: str, value):
        """Gọi từ valueChanged callback của các slider mixer."""
        self._slider_debouncer.push(slider_key, value)

    def _on_slider_settled(self, key: str, value):
        label = self._slider_label_map.get(key, key)
        try:
            self.announce_state(f"{label} {int(value)}")
        except Exception:
            self.announce_state(f"{label} {value}")

    # ── Wiring vào engine + dashboard ───────────────────────

    def hook_dashboard_signals(self):
        """
        Gắn callback vào các signal hiện có:
          - MIDI status changes
          - Tone detection result
          - Score result
          - Generic message popup
        """
        d = self._dashboard
        speaker = self._speaker

        # MIDI status
        try:
            d._midi_status_signal.connect(self._on_midi_status_changed)
        except Exception as e:
            log.debug("Không hook được _midi_status_signal: %s", e)

        # Tone detection result
        try:
            d._tone_result_signal.connect(self._on_tone_result)
        except Exception as e:
            log.debug("Không hook được _tone_result_signal: %s", e)

        # Score
        try:
            d._score_report_signal.connect(self._on_score_report)
        except Exception as e:
            log.debug("Không hook được _score_report_signal: %s", e)

        # Message
        try:
            d._message_signal.connect(self._on_message)
        except Exception as e:
            log.debug("Không hook được _message_signal: %s", e)

        # Browser status
        try:
            d._browser_status_signal.connect(self._on_browser_status_changed)
        except Exception as e:
            log.debug("Không hook được _browser_status_signal: %s", e)

    # ── Slot handlers ───────────────────────────────────────

    def _on_midi_status_changed(self):
        try:
            connected = self._dashboard.engine.is_midi_connected()
        except Exception:
            return
        self.announce_state("MIDI đã kết nối" if connected else "Mất kết nối MIDI")

    def _on_browser_status_changed(self):
        try:
            engine = self._dashboard.engine
            connected = bool(getattr(engine.cdp_monitor, "is_connected", False))
        except Exception:
            return
        if connected:
            self.announce_state("Đã kết nối trình duyệt")

    def _on_tone_result(self, result: dict):
        if not isinstance(result, dict):
            return
        if "error" in result:
            self.announce_error(f"Lỗi dò tone: {result['error']}")
            return
        key = result.get("key") or result.get("key_display") or ""
        scale = result.get("scale", "")
        conf = result.get("confidence", None)
        text_parts = []
        if key:
            text_parts.append(f"Phát hiện tone {key_to_vn(key, scale)}")
        if conf is not None:
            try:
                pct = int(round(float(conf) * 100)) if float(conf) <= 1.0 else int(conf)
                text_parts.append(f"độ tin cậy {pct} phần trăm")
            except Exception:
                pass
        if text_parts:
            self.announce_state(", ".join(text_parts))

    def _on_score_report(self, result: dict):
        if not isinstance(result, dict):
            return
        score = result.get("score") or result.get("total") or result.get("final_score")
        if score is None:
            return
        try:
            n = int(round(float(score)))
        except Exception:
            return
        rank = "xuất sắc" if n >= 90 else "tốt" if n >= 75 else "trung bình" if n >= 50 else "cần cố gắng"
        self.announce_state(f"Điểm {n}, {rank}")

    def _on_message(self, text: str, is_error: bool):
        if not text:
            return
        # Loại bỏ emoji thường gặp ở đầu để TTS không đọc dấu lạ.
        clean = text.lstrip("✅❌⚠️💾🎵🎭♪🙈👁️ ").strip()
        if is_error:
            self.announce_error(clean)
        else:
            self.announce_state(clean)
