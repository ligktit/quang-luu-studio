"""
ui.components.audio_pulse
=========================
Nguồn nhịp audio DÙNG CHUNG (singleton) cho hiệu ứng "lấp lánh theo nhạc".

- Bắt WASAPI loopback MỘT LẦN trong thread nền (fail-soft nếu thiếu pyaudiowpatch).
- Tính `level` (năng lượng RMS đã làm mượt, 0..1) + phát hiện `beat` (onset năng lượng).
- QTimer ở main-thread phát signal `pulse(level: float, beat: bool)` ~30fps để các
  widget (nút, visualizer) animate đồng bộ mà không tự bắt audio riêng.

Dùng:
    ap = AudioPulse.instance(); ap.start()
    ap.pulse.connect(slot)        # slot(level, beat)
    buf = ap.latest_buffer()      # np.ndarray 256 điểm cho visualizer

Tham chiếu đếm start/stop: nhiều widget cùng dùng, capture chỉ dừng khi không ai dùng.
"""
from __future__ import annotations

import math
import threading

import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

POINTS = 256


class AudioPulse(QObject):
    pulse = Signal(float, bool)   # (level 0..1, beat)

    _inst = None

    def __init__(self):
        super().__init__()
        self._buffer = np.zeros(POINTS, dtype=np.float32)
        self._level = 0.0           # mức đã làm mượt (0..1)
        self._energy_ema = 0.0      # trung bình trượt năng lượng (cho beat)
        self._beat_pending = False
        self._last_beat_t = 0.0
        self._refcount = 0
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._emit_tick)

    @classmethod
    def instance(cls) -> "AudioPulse":
        if cls._inst is None:
            cls._inst = AudioPulse()
        return cls._inst

    # ── Lifecycle (ref-counted) ──────────────────────────────
    def start(self):
        self._refcount += 1
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="audio-pulse")
        self._thread.start()
        self._timer.start(33)

    def stop(self):
        self._refcount = max(0, self._refcount - 1)
        if self._refcount > 0:
            return
        self._running = False
        self._timer.stop()

    # ── Data cho visualizer ──────────────────────────────────
    def latest_buffer(self) -> np.ndarray:
        return self._buffer

    def level(self) -> float:
        return self._level

    # ── Main-thread tick: phát signal ────────────────────────
    def _emit_tick(self):
        beat = False
        with self._lock:
            if self._beat_pending:
                beat = True
                self._beat_pending = False
            level = self._level
        self.pulse.emit(level, beat)

    # ── Capture + phân tích (thread nền) ─────────────────────
    def _capture_loop(self):
        try:
            import time
            import pyaudiowpatch as paw
            pa = paw.PyAudio()
            wasapi = None
            for i in range(pa.get_host_api_count()):
                api = pa.get_host_api_info_by_index(i)
                if api.get("name", "").startswith("Windows WASAPI"):
                    wasapi = api
                    break
            if not wasapi:
                pa.terminate()
                return
            spk = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
            dev = None
            for i in range(pa.get_device_count()):
                d = pa.get_device_info_by_index(i)
                if d.get("isLoopbackDevice", False) and d["name"].startswith(spk["name"][:20]):
                    dev = d
                    break
            dev = dev or spk
            ch = max(1, int(dev.get("maxInputChannels", 2)))
            rate = int(dev.get("defaultSampleRate", 44100))
            chunk = POINTS * 2
            stream = pa.open(format=paw.paFloat32, channels=ch, rate=rate, input=True,
                             input_device_index=int(dev["index"]), frames_per_buffer=chunk)
            while self._running:
                try:
                    data = stream.read(chunk, exception_on_overflow=False)
                    s = np.frombuffer(data, dtype=np.float32)
                    if ch > 1:
                        s = s.reshape(-1, ch).mean(axis=1)
                    # Buffer hiển thị
                    if len(s) >= POINTS:
                        step = len(s) // POINTS
                        buf = s[::step][:POINTS]
                    else:
                        buf = np.zeros(POINTS, dtype=np.float32)
                        buf[:len(s)] = s
                    self._buffer = buf
                    self._analyze(buf, time.time())
                except Exception:
                    break
            stream.stop_stream(); stream.close(); pa.terminate()
        except Exception:
            pass  # không có pyaudiowpatch / lỗi device → level giữ 0, không beat

    def _analyze(self, buf: np.ndarray, now: float):
        """Tính level mượt + phát hiện beat (onset năng lượng đơn giản)."""
        energy = float(np.sqrt(np.mean(buf * buf)) if buf.size else 0.0)
        # Level: scale + EMA làm mượt để glow không giật
        target = min(1.0, energy * 3.2)
        with self._lock:
            self._level += (target - self._level) * 0.35
            # Beat: năng lượng vượt hẳn trung bình trượt + đủ to + qua refractory
            ema = self._energy_ema
            self._energy_ema = ema + (energy - ema) * 0.25
            is_beat = (energy > ema * 1.45 and energy > 0.015
                       and (now - self._last_beat_t) > 0.18)
            if is_beat:
                self._last_beat_t = now
                self._beat_pending = True
