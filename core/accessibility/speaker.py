"""
core.accessibility.speaker
==========================
TTS engine wrapper (pyttsx3 + SAPI5 trên Windows).

Đặc điểm:
- Async: chạy trong worker thread + queue → không block UI.
- Priority: "high" flush queue (cho lỗi / thông báo khẩn).
- Fail-soft: pyttsx3 chưa cài thì Speaker trở thành no-op stub,
  app vẫn khởi động bình thường.
- Singleton qua get_speaker() để mọi module dùng chung 1 engine.
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

log = logging.getLogger("accessibility.speaker")

try:
    import pyttsx3  # type: ignore
    _PYTTSX3_AVAILABLE = True
except Exception as e:  # pragma: no cover — môi trường không cài pyttsx3
    pyttsx3 = None
    _PYTTSX3_AVAILABLE = False
    log.info("pyttsx3 không khả dụng (%s) — TTS sẽ là no-op", e)


# Sentinel cho việc flush queue.
_FLUSH = object()


class Speaker:
    """
    TTS engine với queue + worker thread.

    Lifecycle:
        spk = Speaker(rate=180)
        spk.start()
        spk.speak("Xin chào")
        spk.speak("Lỗi nghiêm trọng", priority="high")  # flush queue
        spk.stop()

    Mọi method đều thread-safe.
    """

    def __init__(self, rate: int = 180, voice_id: str = "", enabled: bool = True):
        self._rate = int(rate)
        self._voice_id = voice_id or ""
        self._enabled = bool(enabled) and _PYTTSX3_AVAILABLE
        self._engine = None
        self._queue: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()
        self._last_text = ""

    # ── Public API ───────────────────────────────────────────

    @property
    def available(self) -> bool:
        """True nếu pyttsx3 có sẵn (engine có thể nói)."""
        return _PYTTSX3_AVAILABLE

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool):
        self._enabled = bool(value) and _PYTTSX3_AVAILABLE

    def start(self):
        """Khởi tạo engine + worker thread. Idempotent."""
        if not _PYTTSX3_AVAILABLE:
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_flag.clear()
            self._thread = threading.Thread(
                target=self._run, name="tts-worker", daemon=True
            )
            self._thread.start()

    def speak(self, text: str, priority: str = "normal"):
        """
        Đẩy text vào hàng đợi để TTS đọc.
        priority="high" → flush queue trước khi đẩy text vào (đọc ngay).
        """
        if not self._enabled or not text:
            return
        if priority == "high":
            # Flush queue: đẩy sentinel để worker bỏ qua các item cũ.
            self._queue.put(_FLUSH)
        # Tránh đọc trùng câu liên tiếp (vd: focus đi-về cùng widget).
        if text == self._last_text and priority != "high":
            return
        self._last_text = text
        self._queue.put(text)

    def stop(self):
        """Dừng worker thread + engine. Idempotent."""
        self._stop_flag.set()
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass

    def set_rate(self, rate: int):
        self._rate = int(rate)
        if self._engine is not None:
            try:
                self._engine.setProperty("rate", self._rate)
            except Exception:
                pass

    def set_voice(self, voice_id: str):
        self._voice_id = voice_id or ""
        if self._engine is not None and self._voice_id:
            try:
                self._engine.setProperty("voice", self._voice_id)
            except Exception:
                pass

    def list_voices(self):
        """Trả về list tuple (voice_id, name, lang) — dùng cho settings dialog."""
        if not _PYTTSX3_AVAILABLE:
            return []
        try:
            engine = self._engine or pyttsx3.init()
            voices = engine.getProperty("voices") or []
            out = []
            for v in voices:
                lang = ""
                try:
                    if v.languages:
                        lang = str(v.languages[0])
                except Exception:
                    pass
                out.append((v.id, getattr(v, "name", v.id), lang))
            return out
        except Exception as e:
            log.warning("list_voices lỗi: %s", e)
            return []

    # ── Worker ───────────────────────────────────────────────

    def _init_engine(self):
        if self._engine is not None:
            return
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._rate)
            if self._voice_id:
                try:
                    self._engine.setProperty("voice", self._voice_id)
                except Exception:
                    pass
            else:
                # Tự chọn voice tiếng Việt nếu có
                vid = self._auto_pick_vietnamese_voice()
                if vid:
                    try:
                        self._engine.setProperty("voice", vid)
                        self._voice_id = vid
                    except Exception:
                        pass
        except Exception as e:
            log.warning("Không khởi tạo được pyttsx3 engine: %s", e)
            self._engine = None

    def _auto_pick_vietnamese_voice(self) -> str:
        """Tìm voice An / Linh / Mai / vi-VN trong SAPI5."""
        try:
            engine = self._engine or pyttsx3.init()
            voices = engine.getProperty("voices") or []
            keywords = ("vietnam", "vi-vn", " an ", "anan", "linh", "mai", "vietna")
            for v in voices:
                name = (getattr(v, "name", "") or "").lower()
                vid = (getattr(v, "id", "") or "").lower()
                if any(k in name or k in vid for k in keywords):
                    return v.id
        except Exception:
            pass
        return ""

    def _run(self):
        self._init_engine()
        if self._engine is None:
            return
        while not self._stop_flag.is_set():
            try:
                item = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if item is None:
                break
            if item is _FLUSH:
                # Drain các text còn trong queue trước khi nói item mới.
                try:
                    while True:
                        self._queue.get_nowait()
                except queue.Empty:
                    pass
                continue
            try:
                self._engine.say(item)
                self._engine.runAndWait()
            except RuntimeError:
                # pyttsx3 đôi khi raise nếu engine đang busy — ignore.
                pass
            except Exception as e:
                log.debug("TTS speak error: %s", e)


# ── Singleton ────────────────────────────────────────────────
_singleton: Optional[Speaker] = None
_singleton_lock = threading.Lock()


def get_speaker(rate: int = 180, voice_id: str = "", enabled: bool = False) -> Speaker:
    """Trả về Speaker dùng chung. Lần đầu gọi sẽ khởi tạo + start nếu enabled."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = Speaker(rate=rate, voice_id=voice_id, enabled=enabled)
            if enabled:
                _singleton.start()
        return _singleton
