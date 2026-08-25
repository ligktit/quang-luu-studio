"""
Chạy trọn vòng thu của recorder_worker với thiết bị audio giả.

Bao trọn đường đi thật: callback → queue → drain → resample mic → trộn →
limiter → file WAV. Tình huống dựng đúng ca hay gây rè nhất: mic 44.1kHz +
loa 48kHz, cả hai nguồn đều gần đỉnh.
"""
import os
import sys
import threading
import time
import wave

import numpy as np
import pytest

import recorder_worker

PA_CONTINUE = 0
PA_INT16 = 8


class _FakeStream:
    """Bơm sine vào stream_callback theo nhịp gần thời gian thực."""

    def __init__(self, callback, chunk, channels, rate, freq, amplitude):
        self._callback = callback
        self._chunk = chunk
        self._channels = channels
        self._rate = rate
        self._freq = freq
        self._amp = amplitude
        self._running = False
        self._thread = None
        self._phase = 0

    def _block(self):
        n = self._phase + np.arange(self._chunk)
        self._phase += self._chunk
        mono = np.sin(2 * np.pi * self._freq * n / self._rate) * self._amp
        frames = np.repeat(mono[:, None], self._channels, axis=1)
        return frames.astype(np.int16).tobytes()

    def _pump(self):
        period = self._chunk / self._rate
        while self._running:
            self._callback(self._block(), self._chunk, None, 0)
            time.sleep(period)

    def start_stream(self):
        self._running = True
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def stop_stream(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

    def close(self):
        self.stop_stream()


class _FakePyAudio:
    DEVICES = {
        0: {"index": 0, "name": "Loa [Loopback]", "maxInputChannels": 2,
            "maxOutputChannels": 0, "defaultSampleRate": 48000.0,
            "isLoopbackDevice": True, "hostApi": 0},
        1: {"index": 1, "name": "Mic USB", "maxInputChannels": 1,
            "maxOutputChannels": 0, "defaultSampleRate": 44100.0,
            "isLoopbackDevice": False, "hostApi": 0},
    }

    def __init__(self):
        self.streams = []

    def get_device_count(self):
        return len(self.DEVICES)

    def get_device_info_by_index(self, idx):
        return dict(self.DEVICES[idx])

    def get_format_from_width(self, width):
        assert width == 2
        return PA_INT16

    def get_sample_size(self, fmt):
        return 2

    def open(self, format=None, channels=None, rate=None, input=None,
             input_device_index=None, frames_per_buffer=None,
             stream_callback=None):
        # Nguồn nhạc gần đỉnh, giọng cũng gần đỉnh → tổng chắc chắn vượt trần
        freq, amp = (220.0, 30000) if input_device_index == 0 else (440.0, 28000)
        stream = _FakeStream(stream_callback, frames_per_buffer, channels,
                             rate, freq, amp)
        self.streams.append(stream)
        return stream

    def terminate(self):
        pass


@pytest.fixture
def fake_pyaudio(monkeypatch):
    module = type(sys)("pyaudiowpatch")
    module.PyAudio = _FakePyAudio
    module.paContinue = PA_CONTINUE
    module.paInt16 = PA_INT16
    monkeypatch.setitem(sys.modules, "pyaudiowpatch", module)
    return module


def _record(tmp_path, seconds=1.0):
    out_path = tmp_path / "rec.wav"
    flag_path = tmp_path / ".flag"
    flag_path.write_text("recording")

    def _stop_later():
        time.sleep(seconds)
        os.remove(flag_path)

    threading.Thread(target=_stop_later, daemon=True).start()

    old_argv = sys.argv[:]
    sys.argv = ["recorder_worker.py", str(out_path), str(flag_path), "0", "1"]
    try:
        recorder_worker.main()
    finally:
        sys.argv = old_argv

    with wave.open(str(out_path), "rb") as wf:
        params = wf.getparams()
        raw = wf.readframes(wf.getnframes())
    return params, np.frombuffer(raw, dtype=np.int16).reshape(-1, 2)


def test_thu_tron_hai_nguon_ra_wav_hop_le(tmp_path, fake_pyaudio):
    params, audio = _record(tmp_path)

    assert params.nchannels == 2
    assert params.sampwidth == 2
    assert params.framerate == 48000
    # Thu ~1 giây; nới rộng biên vì phụ thuộc lịch chạy của máy CI
    assert 0.4 * 48000 < audio.shape[0] < 2.0 * 48000


def test_khong_con_cat_cung_dinh_song(tmp_path, fake_pyaudio):
    """Trước khi sửa, tổng 2 nguồn bị np.clip → hàng loạt mẫu nằm bẹt ở ±32767."""
    _, audio = _record(tmp_path)

    at_ceiling = np.count_nonzero(np.abs(audio) >= 32767)
    assert at_ceiling == 0
    assert np.max(np.abs(audio)) > 5000   # có tiếng thật, không phải im lặng


def test_thu_khong_mic_giu_nguyen_muc(tmp_path, fake_pyaudio):
    """Mic tắt (-2) → đi thẳng, không hạ gain, không thêm độ trễ nhìn trước."""
    out_path = tmp_path / "rec.wav"
    flag_path = tmp_path / ".flag"
    flag_path.write_text("recording")

    def _stop_later():
        time.sleep(0.8)
        os.remove(flag_path)

    threading.Thread(target=_stop_later, daemon=True).start()

    old_argv = sys.argv[:]
    sys.argv = ["recorder_worker.py", str(out_path), str(flag_path), "0", "-2"]
    try:
        recorder_worker.main()
    finally:
        sys.argv = old_argv

    with wave.open(str(out_path), "rb") as wf:
        audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)

    # Nguồn giả có biên độ 30000 → phải giữ nguyên, không bị hạ
    assert np.max(np.abs(audio)) == pytest.approx(30000, abs=2)
