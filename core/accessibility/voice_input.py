"""
core.accessibility.voice_input
==============================
Voice command (Vosk offline, VI) — push-to-talk Ctrl+Space.

Module fail-soft: nếu Vosk hoặc sounddevice chưa cài, hoặc model chưa được tải,
VoiceInput trả về stub không listen, app vẫn chạy bình thường.

Intent matching dùng keyword đơn giản (không cần ML).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger("accessibility.voice")

try:
    import sounddevice as sd  # type: ignore
    _SD_OK = True
except Exception as e:  # pragma: no cover
    sd = None
    _SD_OK = False
    log.info("sounddevice không khả dụng (%s) — voice command sẽ tắt", e)

try:
    from vosk import Model, KaldiRecognizer  # type: ignore
    _VOSK_OK = True
except Exception as e:  # pragma: no cover
    Model = None
    KaldiRecognizer = None
    _VOSK_OK = False
    log.info("vosk không khả dụng (%s) — voice command sẽ tắt", e)


# ── Intent matcher ────────────────────────────────────────────

@dataclass
class Intent:
    name: str
    text: str  # raw transcript
    arg: Optional[str] = None


_KEYWORD_INTENTS = [
    # (intent_name, list_of_keyword_phrases)
    ("autokey",          ["dò tone", "tự động dò", "do tone", "auto tone"]),
    ("record_toggle",    ["ghi âm", "thu âm", "ghi am", "bắt đầu ghi", "dừng ghi"]),
    ("save",             ["lưu bài", "luu bai", "lưu lại"]),
    ("open_songs",       ["mở bài", "danh sách bài", "mo bai"]),
    ("score",            ["chấm điểm", "cham diem", "tính điểm"]),
    ("speak_status",     ["đọc trạng thái", "doc trang thai", "trạng thái"]),
    ("stop_tts",         ["tắt giọng", "dừng đọc", "im đi"]),
    ("mute_music",       ["tắt nhạc", "tat nhac", "mute nhạc"]),
    ("mute_mic",         ["tắt mic", "tat mic", "mute mic"]),
    ("volume_up_music",  ["tăng nhạc", "tang nhac", "to nhạc"]),
    ("volume_down_music", ["giảm nhạc", "giam nhac", "nhỏ nhạc"]),
    ("volume_up_mic",    ["tăng mic", "tang mic"]),
    ("volume_down_mic",  ["giảm mic", "giam mic"]),
    ("volume_up_reverb", ["tăng vang", "thêm vang"]),
    ("volume_down_reverb", ["giảm vang", "bớt vang"]),
    ("mode_danca",       ["dân ca", "chế độ dân ca"]),
    ("mode_lofi",        ["lofi", "chế độ lofi"]),
    ("mode_remix",       ["remix", "chế độ remix"]),
    ("mode_datheloai",   ["đa thể loại", "đa thể"]),
]


def match_intent(transcript: str) -> Optional[Intent]:
    """Trả về Intent đầu tiên match keyword, hoặc None."""
    if not transcript:
        return None
    t = transcript.strip().lower()
    for name, keys in _KEYWORD_INTENTS:
        for k in keys:
            if k in t:
                return Intent(name=name, text=transcript)
    return None


# ── VoiceInput service ────────────────────────────────────────

class VoiceInput:
    """
    Service push-to-talk: gọi start_listening() khi giữ phím, stop_listening()
    khi thả → match intent → callback.

    on_intent: Callable[[Intent], None]
    on_error:  Callable[[str], None]
    """

    def __init__(self, model_path: str = "", sample_rate: int = 16000,
                 on_intent: Optional[Callable[[Intent], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None):
        self._model_path = model_path or self._default_model_path()
        self._rate = int(sample_rate)
        self._on_intent = on_intent
        self._on_error = on_error
        self._model = None
        self._stream = None
        self._recognizer = None
        self._lock = threading.Lock()
        self._listening = False

    @property
    def available(self) -> bool:
        return _VOSK_OK and _SD_OK and os.path.isdir(self._model_path)

    def _default_model_path(self) -> str:
        # Cho phép placement linh hoạt: project_root/models/vosk-vi/ hoặc next-to-exe.
        import sys
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base, "models", "vosk-vi")

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        if not self.available:
            return False
        try:
            self._model = Model(self._model_path)
            return True
        except Exception as e:
            log.warning("Không load được Vosk model %s: %s", self._model_path, e)
            if self._on_error:
                self._on_error(f"Không load được model giọng nói: {e}")
            return False

    # ── Push-to-talk API ────────────────────────────────────

    def start_listening(self):
        with self._lock:
            if self._listening:
                return
            if not self._ensure_model():
                return
            self._listening = True
            self._recognizer = KaldiRecognizer(self._model, self._rate)
            try:
                self._stream = sd.RawInputStream(
                    samplerate=self._rate, blocksize=8000, dtype="int16",
                    channels=1, callback=self._on_audio,
                )
                self._stream.start()
            except Exception as e:
                self._listening = False
                if self._on_error:
                    self._on_error(f"Không mở được mic: {e}")
                log.warning("Voice input mic open lỗi: %s", e)

    def stop_listening(self):
        with self._lock:
            if not self._listening:
                return
            self._listening = False
            try:
                if self._stream is not None:
                    self._stream.stop()
                    self._stream.close()
            except Exception:
                pass
            self._stream = None

            # Lấy final result
            transcript = ""
            try:
                if self._recognizer is not None:
                    res = self._recognizer.FinalResult()
                    transcript = (json.loads(res) or {}).get("text", "")
            except Exception:
                transcript = ""
            self._recognizer = None

            if transcript and self._on_intent:
                intent = match_intent(transcript)
                if intent is not None:
                    intent.text = transcript
                    self._on_intent(intent)
                else:
                    # Vẫn gửi intent "unknown" để frontend phản hồi "Không hiểu lệnh"
                    self._on_intent(Intent(name="unknown", text=transcript))

    # ── sounddevice callback ────────────────────────────────

    def _on_audio(self, indata, frames, time_info, status):
        try:
            if self._recognizer is not None:
                self._recognizer.AcceptWaveform(bytes(indata))
        except Exception as e:
            log.debug("Voice input audio callback lỗi: %s", e)
