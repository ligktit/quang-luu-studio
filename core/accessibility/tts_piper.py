"""
core.accessibility.tts_piper
============================
Backend TTS neural tiếng Việt dùng **Piper** (binary subprocess, offline).

Vì sao binary thay vì pip `piper-tts`:
- Không kéo onnxruntime/piper_phonemize vào app (đóng gói PyInstaller nhẹ, ổn định).
- Hợp kiến trúc bundle-binary sẵn có (ffmpeg, studio_one...).

Cách hoạt động: chạy `piper(.exe) -m <voice>.onnx --output-raw`, ghi text vào
stdin, đọc PCM int16 mono (sample_rate lấy từ <voice>.onnx.json) ở stdout rồi
phát qua sounddevice. Đồng bộ (blocking) — gọi từ worker thread của Speaker.

Module fail-soft: thiếu piper binary / voice / sounddevice → `available=False`,
Speaker tự fallback sang SAPI.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading

log = logging.getLogger("accessibility.tts_piper")

try:
    import numpy as np  # type: ignore
    import sounddevice as sd  # type: ignore
    _AUDIO_OK = True
except Exception as e:  # pragma: no cover
    np = None
    sd = None
    _AUDIO_OK = False
    log.info("sounddevice/numpy không khả dụng (%s) — Piper TTS sẽ tắt", e)


def _candidate_bases() -> list:
    """Các thư mục gốc có thể chứa models/ + tools/piper. Frozen onefile: ưu tiên
    cạnh exe (installer ship), rồi _MEIPASS (nếu bundle); dev: project root."""
    bases = []
    if getattr(sys, "frozen", False):
        bases.append(os.path.dirname(sys.executable))
        mei = getattr(sys, "_MEIPASS", None)
        if mei:
            bases.append(mei)
    bases.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return bases


def _find_piper_binary() -> str:
    """Tìm piper(.exe) trong các base (tools/piper) hoặc PATH. "" nếu không thấy."""
    exe = "piper.exe" if os.name == "nt" else "piper"
    for base in _candidate_bases():
        for c in (os.path.join(base, "tools", "piper", exe), os.path.join(base, "piper", exe)):
            if os.path.isfile(c):
                return c
    from shutil import which
    return which(exe) or ""


def _find_voice(voice_dir: str = "", voice_id: str = "") -> str:
    """Tìm file voice .onnx. Ưu tiên voice_id cụ thể, nếu không lấy .onnx đầu tiên
    trong models/piper-vi/ (quét qua các base)."""
    dirs = [voice_dir] if voice_dir else [os.path.join(b, "models", "piper-vi") for b in _candidate_bases()]
    for vdir in dirs:
        if not vdir or not os.path.isdir(vdir):
            continue
        if voice_id:
            p = os.path.join(vdir, voice_id if voice_id.endswith(".onnx") else f"{voice_id}.onnx")
            if os.path.isfile(p):
                return p
        for fn in sorted(os.listdir(vdir)):
            if fn.endswith(".onnx"):
                return os.path.join(vdir, fn)
    return ""


def _voice_sample_rate(onnx_path: str) -> int:
    """Đọc sample_rate từ <voice>.onnx.json (mặc định Piper 22050)."""
    cfg_path = onnx_path + ".json"
    try:
        with open(cfg_path, encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("audio", {}).get("sample_rate", 22050))
    except Exception:
        return 22050


class PiperTTS:
    """Backend Piper đồng bộ. Dùng trong Speaker khi engine='piper'."""

    def __init__(self, voice_id: str = "", voice_dir: str = ""):
        self._binary = _find_piper_binary()
        self._voice = _find_voice(voice_dir, voice_id)
        self._rate = _voice_sample_rate(self._voice) if self._voice else 22050
        self._proc_lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._stopped = False

    @property
    def available(self) -> bool:
        return bool(_AUDIO_OK and self._binary and self._voice)

    def describe(self) -> str:
        if not _AUDIO_OK:
            return "Thiếu sounddevice/numpy"
        if not self._binary:
            return "Chưa có piper binary (tools/piper/)"
        if not self._voice:
            return "Chưa có voice .onnx (models/piper-vi/)"
        return f"Piper: {os.path.basename(self._voice)} @ {self._rate}Hz"

    def set_voice(self, voice_id: str = "", voice_dir: str = ""):
        v = _find_voice(voice_dir, voice_id)
        if v:
            self._voice = v
            self._rate = _voice_sample_rate(v)

    def speak_blocking(self, text: str):
        """Synthesize + phát, CHẶN tới khi đọc xong (hoặc bị stop())."""
        if not self.available or not text:
            return
        self._stopped = False
        try:
            pcm = self._synth(text)
        except Exception as e:
            log.warning("Piper synth lỗi: %s", e)
            return
        if pcm is None or self._stopped:
            return
        try:
            audio = np.frombuffer(pcm, dtype=np.int16)
            if audio.size == 0:
                return
            sd.play(audio, self._rate)
            sd.wait()
        except Exception as e:
            log.debug("Piper playback lỗi: %s", e)

    def _synth(self, text: str) -> bytes | None:
        """Chạy piper, trả PCM int16 mono thô (stdout)."""
        cmd = [self._binary, "-m", self._voice, "--output-raw"]
        creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        with self._proc_lock:
            if self._stopped:
                return None
            self._proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, creationflags=creationflags,
            )
        try:
            out, _ = self._proc.communicate(input=text.encode("utf-8"), timeout=30)
            return out
        except Exception as e:
            log.debug("Piper process lỗi: %s", e)
            try:
                self._proc.kill()
            except Exception:
                pass
            return None
        finally:
            with self._proc_lock:
                self._proc = None

    def stop(self):
        """Ngắt ngay: kill piper đang chạy + dừng phát."""
        self._stopped = True
        with self._proc_lock:
            if self._proc is not None:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        if _AUDIO_OK:
            try:
                sd.stop()
            except Exception:
                pass
