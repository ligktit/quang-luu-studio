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
    # (intent_name, list_of_keyword_phrases — biến thể gồm cả có dấu, không dấu, và lỗi
    #  thường gặp của Vosk small-vn để fuzzy match dễ hơn)
    ("autokey",           ["dò tone", "tự động dò", "do tone", "auto tone",
                           "do ton", "dò ton", "đo tone", "đò tone", "dò tôn",
                           "dò ra tone", "phát hiện tone"]),
    ("record_toggle",     ["ghi âm", "thu âm", "ghi am", "bắt đầu ghi", "dừng ghi",
                           "ghi", "thu", "record"]),
    ("save",              ["lưu bài", "luu bai", "lưu lại", "lưu", "save"]),
    ("open_songs",        ["mở bài", "danh sách bài", "mo bai", "danh sách",
                           "mở danh sách", "list bài", "danh sach"]),
    ("score",             ["chấm điểm", "cham diem", "tính điểm", "tinh diem",
                           "điểm", "chấm"]),
    ("speak_status",      ["đọc trạng thái", "doc trang thai", "trạng thái",
                           "trang thai", "đọc trạng"]),
    ("stop_tts",          ["tắt giọng", "dừng đọc", "im đi", "im lặng",
                           "tat giong", "dung doc"]),
    ("mute_music",        ["tắt nhạc", "tat nhac", "mute nhạc", "tắt bài",
                           "tắt nhạc nền"]),
    ("mute_mic",          ["tắt mic", "tat mic", "mute mic", "tắt micro"]),
    ("volume_up_music",   ["tăng nhạc", "tang nhac", "to nhạc", "lớn nhạc",
                           "to lên nhạc", "nhạc to"]),
    ("volume_down_music", ["giảm nhạc", "giam nhac", "nhỏ nhạc", "bớt nhạc",
                           "nhạc nhỏ"]),
    ("volume_up_mic",     ["tăng mic", "tang mic", "to mic", "lớn mic"]),
    ("volume_down_mic",   ["giảm mic", "giam mic", "nhỏ mic", "bớt mic"]),
    ("volume_up_reverb",  ["tăng vang", "thêm vang", "to vang", "lớn vang"]),
    ("volume_down_reverb", ["giảm vang", "bớt vang", "nhỏ vang"]),
    ("mode_danca",        ["dân ca", "chế độ dân ca", "dan ca"]),
    ("mode_lofi",         ["lofi", "chế độ lofi", "lo fi"]),
    ("mode_remix",        ["remix", "chế độ remix", "rờ mít"]),
    ("mode_datheloai",    ["đa thể loại", "đa thể", "da the loai", "tổng hợp"]),
]


# Toàn bộ phrase phẳng — dùng cho Vosk grammar + fuzzy match
def all_phrases():
    out = []
    for _, keys in _KEYWORD_INTENTS:
        out.extend(keys)
    return out


# Tạo grammar JSON cho Vosk — limit vocabulary chỉ trong các lệnh đã biết.
# "[unk]" cho phép Vosk fallback từ ngoài grammar (rất quan trọng — không có
# nó, từ lạ sẽ làm recognizer nhầm thành lệnh ngẫu nhiên).
def build_vosk_grammar() -> str:
    phrases = all_phrases()
    # Phá phrase thành từ riêng để Vosk small model nhận diện tốt hơn
    words = set()
    for p in phrases:
        for w in p.split():
            words.add(w)
    # Vẫn giữ luôn phrase đầy đủ cho recognizer ưu tiên
    items = list(words) + phrases + ["[unk]"]
    return json.dumps(items, ensure_ascii=False)


def _normalize(text: str) -> str:
    """Chuẩn hoá để so sánh — bỏ dấu, lowercase, gộp space."""
    if not text:
        return ""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    no_accent = "".join(c for c in nfkd if not unicodedata.combining(c))
    # đ/Đ không bị NFKD bóc dấu — replace thủ công
    no_accent = no_accent.replace("đ", "d").replace("Đ", "D")
    return " ".join(no_accent.lower().split())


def _word_overlap_score(query_norm: str, target_norm: str) -> float:
    """Trả về 0..1 — tỷ lệ từ trong target xuất hiện trong query."""
    q_words = set(query_norm.split())
    t_words = target_norm.split()
    if not t_words:
        return 0.0
    matched = sum(1 for w in t_words if w in q_words)
    return matched / len(t_words)


def match_intent(transcript: str) -> Optional[Intent]:
    """
    Match intent với 2 cấp:
    1. Substring đơn giản (sau khi normalize bỏ dấu).
    2. Word-overlap: nếu >=70% từ trong phrase target xuất hiện trong transcript.
    """
    if not transcript:
        return None
    t_norm = _normalize(transcript)

    # Cấp 1: substring match (đã normalize)
    for name, keys in _KEYWORD_INTENTS:
        for k in keys:
            k_norm = _normalize(k)
            if k_norm and k_norm in t_norm:
                return Intent(name=name, text=transcript)

    # Cấp 2: word-overlap >= 0.7 (cho trường hợp Vosk thiếu/thừa từ)
    best_intent = None
    best_score = 0.0
    for name, keys in _KEYWORD_INTENTS:
        for k in keys:
            k_norm = _normalize(k)
            score = _word_overlap_score(t_norm, k_norm)
            if score >= 0.7 and score > best_score:
                best_score = score
                best_intent = Intent(name=name, text=transcript)
    return best_intent


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
                print("[VOICE] start_listening bỏ qua — model chưa sẵn sàng")
                return
            self._listening = True
            # Grammar-constrained recognizer: tăng độ chính xác đáng kể vì
            # Vosk chỉ phải chọn giữa các lệnh đã biết thay vì toàn bộ vocab.
            try:
                grammar = build_vosk_grammar()
                self._recognizer = KaldiRecognizer(self._model, self._rate, grammar)
            except Exception as e:
                # Một vài Vosk build cũ không hỗ trợ grammar — fallback open vocab
                print(f"[VOICE] grammar không khả dụng ({e}) — dùng vocab mở")
                self._recognizer = KaldiRecognizer(self._model, self._rate)
            try:
                self._stream = sd.RawInputStream(
                    samplerate=self._rate, blocksize=4000, dtype="int16",
                    channels=1, callback=self._on_audio,
                )
                self._stream.start()
                print(f"[VOICE] >>> Bắt đầu nghe (rate={self._rate}, grammar=on)")
            except Exception as e:
                self._listening = False
                if self._on_error:
                    self._on_error(f"Không mở được mic: {e}")
                log.warning("Voice input mic open lỗi: %s", e)
                print(f"[VOICE] !!! Lỗi mở mic: {e}")

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
            raw_json = ""
            try:
                if self._recognizer is not None:
                    raw_json = self._recognizer.FinalResult()
                    transcript = (json.loads(raw_json) or {}).get("text", "")
            except Exception as e:
                print(f"[VOICE] !!! Lỗi parse kết quả: {e}")
                transcript = ""
            self._recognizer = None

            print(f"[VOICE] <<< Dừng nghe. Transcript: {transcript!r}")
            if not transcript:
                print(f"[VOICE]     (raw JSON: {raw_json})")
                if self._on_intent:
                    self._on_intent(Intent(name="empty", text=""))
                return

            if self._on_intent:
                intent = match_intent(transcript)
                if intent is not None:
                    intent.text = transcript
                    print(f"[VOICE]     -> Match intent: {intent.name}")
                    self._on_intent(intent)
                else:
                    print(f"[VOICE]     -> Không match intent nào")
                    self._on_intent(Intent(name="unknown", text=transcript))

    # ── sounddevice callback ────────────────────────────────

    def _on_audio(self, indata, frames, time_info, status):
        try:
            if self._recognizer is not None:
                self._recognizer.AcceptWaveform(bytes(indata))
        except Exception as e:
            log.debug("Voice input audio callback lỗi: %s", e)
