"""
ui.components.sfx_player
~~~~~~~~~~~~~~~~~~~~~~~~
Phát SFX trong app: bật/tắt từng nút, tắt có fade ngắn, một fader âm lượng chung.

Mỗi SFX (theo id) có tối đa một "voice" đang phát; các SFX khác nhau phát chồng
được. Voice là đối tượng bọc thiết bị âm thanh, giao diện:
    finished  — Signal, phát khi hết file HOẶC media lỗi
    play() / stop() / set_gain(float tuyến tính 0..1)
"""
import os
import threading

from PySide6.QtCore import QObject, QVariantAnimation, Signal

FADE_MS = 300


def _percent_to_gain(percent: float) -> float:
    """Fader 0..100 (thang cảm nhận) → gain tuyến tính cho QAudioOutput."""
    v = max(0.0, min(100.0, float(percent))) / 100.0
    try:
        from PySide6.QtMultimedia import QtAudio
        return QtAudio.convertVolume(
            v, QtAudio.VolumeScale.LogarithmicVolumeScale,
            QtAudio.VolumeScale.LinearVolumeScale)
    except Exception:
        return v * v


class _QtVoice(QObject):
    finished = Signal()

    def __init__(self, path: str):
        super().__init__()
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtCore import QUrl
        self._player = QMediaPlayer(self)
        self._out = QAudioOutput(self)
        self._player.setAudioOutput(self._out)
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(self._on_error)
        self._EndOfMedia = QMediaPlayer.EndOfMedia
        self._InvalidMedia = QMediaPlayer.InvalidMedia

    def play(self):
        self._player.play()

    def stop(self):
        self._player.stop()

    def set_gain(self, g: float):
        self._out.setVolume(g)

    def _on_status(self, status):
        if status in (self._EndOfMedia, self._InvalidMedia):
            self.finished.emit()

    def _on_error(self, error, error_string=""):
        print(f"[SFX] Loi media: {error_string or error}")
        self.finished.emit()


class _WinsoundVoice(QObject):
    """Dự phòng khi QtMultimedia hỏng — chỉ .wav, dừng được nhưng không fade."""
    finished = Signal()

    def __init__(self, path: str):
        super().__init__()
        self._path = path

    def play(self):
        def _run():
            try:
                import winsound
                winsound.PlaySound(self._path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()
        # winsound không báo hết file — đoán theo độ dài wav để nút tự tắt đèn.
        try:
            import wave
            from PySide6.QtCore import QTimer
            with wave.open(self._path) as w:
                ms = int(w.getnframes() * 1000 / max(1, w.getframerate()))
            QTimer.singleShot(ms, self, self.finished.emit)
        except Exception:
            pass

    def stop(self):
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass

    def set_gain(self, g: float):
        pass


def _default_voice(path: str):
    try:
        return _QtVoice(path)
    except Exception as e:
        print(f"[SFX] Loi phat SFX: {e}")
        if path.lower().endswith(".wav"):
            return _WinsoundVoice(path)
        raise


class SfxPlayer(QObject):
    """started(id) / stopped(id) cho nút SFX bật/tắt đèn."""
    started = Signal(str)
    stopped = Signal(str)

    def __init__(self, voice_factory=None, fade_ms: int = FADE_MS, parent=None):
        super().__init__(parent)
        self._factory = voice_factory or _default_voice
        self._fade_ms = fade_ms
        self._gain = 1.0
        self._active: dict = {}     # id -> voice đang phát (chưa fade)
        self._fading: list = []     # giữ ref animation đang fade

    def is_playing(self, sfx_id: str) -> bool:
        return sfx_id in self._active

    def toggle(self, sfx_id: str, path: str):
        if sfx_id in self._active:
            self.stop(sfx_id)
            return
        try:
            voice = self._factory(path)
        except Exception as e:
            print(f"[SFX] Khong phat duoc {os.path.basename(path)}: {e}")
            return
        voice.finished.connect(lambda i=sfx_id, v=voice: self._on_finished(i, v))
        voice.set_gain(self._gain)
        self._active[sfx_id] = voice
        voice.play()
        print(f"[SFX] Playing: {os.path.basename(path)}")
        self.started.emit(sfx_id)

    def stop(self, sfx_id: str):
        voice = self._active.pop(sfx_id, None)
        if voice is None:
            return
        self.stopped.emit(sfx_id)
        self._fade_out(voice)

    def set_volume(self, percent: float):
        self._gain = _percent_to_gain(percent)
        for voice in self._active.values():
            voice.set_gain(self._gain)

    # ── Internal ──────────────────────────────────────────────────
    def _fade_out(self, voice):
        start = self._gain
        anim = QVariantAnimation(self)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setDuration(self._fade_ms)
        # Hết file giữa lúc fade → voice đã dispose, không chạm vào nữa.
        def _step(m):
            if not getattr(voice, "_sfx_disposed", False):
                voice.set_gain(start * float(m))

        anim.valueChanged.connect(_step)

        def _done():
            _step(0.0)
            self._dispose(voice)
            if anim in self._fading:
                self._fading.remove(anim)
            anim.deleteLater()

        anim.finished.connect(_done)
        self._fading.append(anim)
        anim.start()

    def _on_finished(self, sfx_id: str, voice):
        if self._active.get(sfx_id) is voice:
            del self._active[sfx_id]
            self.stopped.emit(sfx_id)
        self._dispose(voice)

    @staticmethod
    def _dispose(voice):
        if getattr(voice, "_sfx_disposed", False):
            return
        voice._sfx_disposed = True
        try:
            voice.finished.disconnect()
        except Exception:
            pass
        voice.stop()
        voice.deleteLater()
