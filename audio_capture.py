"""
Audio Capture Thread — Captures system audio output via WASAPI loopback
using the soundcard library.
"""

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

# NOTE: `soundcard` is imported lazily (inside methods) to avoid a COM
# threading-mode conflict with PyQt5.  The soundcard library initialises COM
# in multi-threaded apartment (MTA) mode at import time, but Qt/OLE requires
# single-threaded apartment (STA) mode.  Deferring the import lets Qt
# initialise COM first; soundcard then detects the existing STA and skips
# its own CoInitializeEx call.


class AudioCaptureThread(QThread):
    """Thread that captures audio from a system output device (loopback)."""

    audio_data = pyqtSignal(np.ndarray)  # Emits mono float32 audio buffer
    error_occurred = pyqtSignal(str)

    def __init__(self, device_id=None, sample_rate=44100, block_size=2048):
        super().__init__()
        self.device_id = device_id
        self.sample_rate = sample_rate
        self.block_size = block_size
        self._running = False

    def set_device(self, device_id):
        """Set the device to capture from."""
        self.device_id = device_id

    def run(self):
        """Main capture loop."""
        import ctypes
        # COM must be initialized on each thread; Qt only initialises it
        # on the main thread, so the worker thread needs its own call.
        ctypes.windll.ole32.CoInitialize(0)
        self._running = True
        try:
            import soundcard as sc  # noqa: lazy import
            # Find the loopback microphone matching the selected speaker ID
            loopback_mic = self._find_loopback(self.device_id)

            if loopback_mic is None:
                self.error_occurred.emit(
                    "Could not find loopback device. "
                    "Make sure you have selected a valid output device."
                )
                return

            with loopback_mic.recorder(
                samplerate=self.sample_rate, channels=1
            ) as recorder:
                while self._running:
                    data = recorder.record(numframes=self.block_size)
                    # data shape: (block_size, channels)
                    mono = data[:, 0].astype(np.float32)
                    self.audio_data.emit(mono)

        except Exception as e:
            if self._running:
                self.error_occurred.emit(str(e))
        finally:
            ctypes.windll.ole32.CoUninitialize()

    def stop(self):
        """Stop the capture thread."""
        self._running = False
        self.wait(2000)

    @staticmethod
    def _find_loopback(device_id):
        """
        Find a loopback microphone corresponding to the given speaker device_id.
        On Windows WASAPI, soundcard exposes loopback captures as microphones
        with isloopback=True.
        """
        import soundcard as sc  # noqa: lazy import
        all_mics = sc.all_microphones(include_loopback=True)

        # Try to match by device_id
        if device_id is not None:
            for mic in all_mics:
                if mic.isloopback and mic.id == device_id:
                    return mic
            # Some systems have different IDs for speaker vs loopback mic,
            # try matching by name similarity
            speakers = sc.all_speakers()
            target_speaker = None
            for s in speakers:
                if s.id == device_id:
                    target_speaker = s
                    break

            if target_speaker:
                target_name = target_speaker.name.lower()
                for mic in all_mics:
                    if mic.isloopback and target_name in mic.name.lower():
                        return mic

        # Fallback: use default speaker's loopback
        try:
            default_speaker = sc.default_speaker()
            default_name = default_speaker.name.lower()
            for mic in all_mics:
                if mic.isloopback and default_name in mic.name.lower():
                    return mic
        except Exception:
            pass

        # Last resort: just grab any loopback
        for mic in all_mics:
            if mic.isloopback:
                return mic

        return None

    @staticmethod
    def get_output_devices():
        """Return list of available output (speaker) devices."""
        devices = []
        try:
            import soundcard as sc  # noqa: lazy import
            speakers = sc.all_speakers()
            for s in speakers:
                devices.append({
                    "id": s.id,
                    "name": s.name,
                })
        except Exception:
            pass
        return devices

    @staticmethod
    def get_default_device_id():
        """Return the default speaker device id."""
        try:
            import soundcard as sc  # noqa: lazy import
            return sc.default_speaker().id
        except Exception:
            return None
