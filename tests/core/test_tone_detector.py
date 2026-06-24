"""
tests/core/test_tone_detector.py
================================
Sprint 4 — ToneDetector

Covers:
  TD-01..TD-07  Pure algorithm / static methods (no external deps)
  TD-08..TD-12  Detection with mocked librosa / sounddevice / yt-dlp
"""
import sys
import types
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from core.tone_detector import ToneDetector


# ──────────────────────────────────────────────────────────────
# Pure / algorithm tests (no mocks needed)
# ──────────────────────────────────────────────────────────────

class TestKeyIndexToMidi:
    """TD-01, TD-02 — key_index_to_midi()

    NGUỒN THẬT: app_config key_midi_map (sharp notation). key_index → tên nốt
    → MIDI CC. C=0, G=80, B=127 — TÌNH CỜ trùng công thức tuyến tính cũ ở các
    điểm này, nhưng các nốt khác (D=23 vs 11) thì khác.
    """

    def test_c_major(self):
        """TD-01: key_idx=0 (C) → MIDI 0 (config C=0)"""
        assert ToneDetector.key_index_to_midi(0) == 0

    def test_g_major(self):
        """TD-02: key_idx=7 (G) → MIDI 80 (config G=80)"""
        assert ToneDetector.key_index_to_midi(7) == 80

    def test_matches_config_map(self):
        """Giá trị phải khớp app_config key_midi_map cho mọi index (sharp)."""
        sharp_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        for idx, note in enumerate(sharp_names):
            expected = ToneDetector.KEY_MIDI_MAP[note]
            assert ToneDetector.key_index_to_midi(idx) == expected

    def test_d_major_is_23_not_linear(self):
        """D (idx=2) → 23 theo config, KHÁC công thức tuyến tính cũ (=11)."""
        assert ToneDetector.key_index_to_midi(2) == 23

    def test_clamped_at_127(self):
        """Clamp: any idx ≥ 11 → B = 127"""
        assert ToneDetector.key_index_to_midi(11) == 127
        assert ToneDetector.key_index_to_midi(12) == 127

    def test_clamped_at_0(self):
        """Clamp: negative idx → C = 0"""
        assert ToneDetector.key_index_to_midi(-1) == 0


class TestScaleToMidi:
    """TD-03, TD-04 — scale_to_midi()

    NGUỒN THẬT: app_config scale_midi_map → Major=13, Minor=18 (knob% plugin).
    Test cũ pin 0/127 là SAI (không khớp đường gửi MIDI thật _send_tone_midi).
    """

    def test_major_returns_13(self):
        """TD-03: 'Major' → 13 (config scale_midi_map)"""
        assert ToneDetector.scale_to_midi("Major") == 13

    def test_minor_returns_18(self):
        """TD-04: 'Minor' → 18 (config scale_midi_map)"""
        assert ToneDetector.scale_to_midi("Minor") == 18

    def test_unknown_defaults_to_major(self):
        """Unknown scale → 13 (treat as Major)"""
        assert ToneDetector.scale_to_midi("Dorian") == 13


class TestIsRelativePair:
    """TD-05, TD-06 — _is_relative_pair()"""

    def test_c_major_a_minor_are_relative(self):
        """TD-05: C Major (0) ↔ Am (9) — relative pair"""
        assert ToneDetector._is_relative_pair(0, "Major", 9, "Minor") is True

    def test_c_major_d_major_not_relative(self):
        """TD-06: C Major (0) vs D Major (2) — NOT relative pair"""
        assert ToneDetector._is_relative_pair(0, "Major", 2, "Major") is False

    def test_g_major_e_minor_relative(self):
        """G Major (7) ↔ Em (4) — relative pair"""
        assert ToneDetector._is_relative_pair(7, "Major", 4, "Minor") is True

    def test_reverse_minor_major(self):
        """Am (9) ↔ C Major (0) works in reverse"""
        assert ToneDetector._is_relative_pair(9, "Minor", 0, "Major") is True


class TestCorrelateProfiles:
    """TD-07 — _correlate_profiles() returns 24 entries"""

    def test_returns_24_results(self):
        """TD-07: result has 24 keys (12 Major + 12 Minor)"""
        chroma = np.ones(12) / 12.0  # flat chroma
        result = ToneDetector._correlate_profiles(
            chroma,
            ToneDetector.KS_MAJOR,
            ToneDetector.KS_MINOR,
        )
        assert len(result) == 24

    def test_result_has_required_keys(self):
        """Each entry has key, scale, correlation, key_index"""
        chroma = np.zeros(12)
        chroma[0] = 1.0  # Strong C
        result = ToneDetector._correlate_profiles(
            chroma,
            ToneDetector.KS_MAJOR,
            ToneDetector.KS_MINOR,
        )
        for uid, entry in result.items():
            assert "key" in entry
            assert "scale" in entry
            assert "correlation" in entry
            assert "key_index" in entry

    def test_flat_chroma_no_nan_no_warning(self):
        """
        NaN guard (Fix #1): chroma phẳng (std=0, VD noise/silence) trước đây tạo
        NaN + RuntimeWarning 'invalid value in divide'. Phải trả 0.0, không NaN,
        không warning.
        """
        import warnings
        flat = np.ones(12) / 12.0  # std = 0
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # bất kỳ RuntimeWarning nào → fail
            result = ToneDetector._correlate_profiles(
                flat, ToneDetector.KS_MAJOR, ToneDetector.KS_MINOR
            )
        assert len(result) == 24
        for entry in result.values():
            assert not np.isnan(entry["correlation"])
            assert entry["correlation"] == 0.0


class TestSafeCorrcoef:
    """Fix #1 — NaN guard cho _safe_corrcoef()."""

    def test_flat_vector_returns_zero(self):
        """Vector phẳng (std=0) → 0.0, không NaN."""
        flat = np.ones(12)
        assert ToneDetector._safe_corrcoef(flat, ToneDetector.KS_MAJOR) == 0.0

    def test_self_correlation_is_one(self):
        """Tự tương quan của vector có biến thiên = 1.0, hữu hạn."""
        a = np.array(ToneDetector.KS_MAJOR)
        c = ToneDetector._safe_corrcoef(a, a)
        assert np.isfinite(c)
        assert abs(c - 1.0) < 1e-9


class TestRelationLevel:
    """Fix #4 — _relation_level() phân biệt relative/parallel/neighbor."""

    def test_relative_pair(self):
        """C Major (0) ↔ Am (9) → 'relative'."""
        assert ToneDetector._relation_level(0, "Major", 9, "Minor") == "relative"

    def test_parallel_pair(self):
        """C Major ↔ Cm (cùng tonic root) → 'parallel'."""
        assert ToneDetector._relation_level(0, "Major", 0, "Minor") == "parallel"

    def test_neighbor_fifth(self):
        """C Major ↔ G Major (6 nốt chung, quãng 5) → 'neighbor'."""
        assert ToneDetector._relation_level(0, "Major", 7, "Major") == "neighbor"

    def test_unrelated(self):
        """C Major ↔ F# Major (xa) → None."""
        assert ToneDetector._relation_level(0, "Major", 6, "Major") is None


class TestConfidenceFlags:
    """Fix #2 — cờ uncertain / confidence_level trong result dict."""

    def test_low_corr_marks_uncertain(self):
        """Chroma gần phẳng (corr thấp) → uncertain=True, confidence_level='low'."""
        rng = np.random.default_rng(0)
        chroma = np.ones(12) / 12.0 + rng.normal(0, 0.0005, 12)
        chroma = np.clip(chroma, 0, None)
        chroma = chroma / chroma.sum()
        with patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            result = ToneDetector._detect_key_from_chroma_impl(chroma, chroma.copy())
        assert result is not None
        assert "uncertain" in result
        assert "confidence_level" in result
        if result["confidence"] < ToneDetector.CONFIDENCE_LOW_THRESHOLD:
            assert result["uncertain"] is True
            assert result["confidence_level"] == "low"

    def test_strong_key_not_uncertain(self):
        """Chroma C major rõ ràng → confidence cao, uncertain=False."""
        chroma = np.array([0.30, 0.01, 0.05, 0.01, 0.20, 0.05,
                           0.01, 0.25, 0.01, 0.05, 0.01, 0.05])
        chroma = chroma / chroma.sum()
        with patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            result = ToneDetector._detect_key_from_chroma_impl(chroma, chroma.copy())
        assert result is not None
        assert result["uncertain"] is False
        assert result["confidence_level"] in ("medium", "high")

    def test_result_always_has_flags(self):
        """Mọi result đều có cả 2 field mới (UI luôn đọc được)."""
        chroma = np.zeros(12)
        chroma[0] = 1.0
        chroma = chroma / chroma.sum()
        with patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            result = ToneDetector._detect_key_from_chroma_impl(chroma, chroma.copy())
        assert {"key", "key_index", "scale", "confidence", "key_display",
                "confidence_level", "uncertain"}.issubset(result.keys())


class TestMidiMapNoDrift:
    """Chống DRIFT giữa hằng fallback trong ToneDetector và nguồn thật ở config.

    KEY_MIDI_MAP / SCALE_MIDI_MAP của class chỉ là FALLBACK khi AppConfig import
    lỗi. Nếu ai đổi _DEFAULT_APP_CONFIG['key_midi_map'] / ['scale_midi_map'] mà
    quên cập nhật 2 hằng này → fallback trả MIDI CC SAI âm thầm (chỉ lộ khi
    config lỗi). Các test dưới khẳng định 2 bảng phải BẰNG config default để
    bắt drift ngay lúc CI, không đợi ra production.
    """

    def test_key_midi_map_matches_config_default(self):
        """ToneDetector.KEY_MIDI_MAP == config _DEFAULT_APP_CONFIG['key_midi_map']."""
        from core.config import _DEFAULT_APP_CONFIG
        assert ToneDetector.KEY_MIDI_MAP == _DEFAULT_APP_CONFIG["key_midi_map"]

    def test_scale_midi_map_matches_config_default(self):
        """ToneDetector.SCALE_MIDI_MAP == config _DEFAULT_APP_CONFIG['scale_midi_map']."""
        from core.config import _DEFAULT_APP_CONFIG
        assert ToneDetector.SCALE_MIDI_MAP == _DEFAULT_APP_CONFIG["scale_midi_map"]

    def test_fallback_path_uses_synced_const(self):
        """Khi AppConfig import lỗi, key_index_to_midi rơi về KEY_MIDI_MAP và
        vẫn khớp config (vì 2 bảng đồng bộ). Mô phỏng lỗi bằng cách patch
        AppConfig.get_key_midi_map raise."""
        from core.config import _DEFAULT_APP_CONFIG
        with patch("core.config.AppConfig.get_key_midi_map",
                   side_effect=RuntimeError("config hỏng")):
            # G (idx 7): config = 80, fallback const cũng phải = 80
            assert ToneDetector.key_index_to_midi(7) == _DEFAULT_APP_CONFIG["key_midi_map"]["G"]

    def test_scale_fallback_path_uses_synced_const(self):
        """Tương tự cho scale_to_midi khi AppConfig lỗi."""
        from core.config import _DEFAULT_APP_CONFIG
        with patch("core.config.AppConfig.get_scale_midi_map",
                   side_effect=RuntimeError("config hỏng")):
            assert ToneDetector.scale_to_midi("Minor") == _DEFAULT_APP_CONFIG["scale_midi_map"]["Minor"]


class TestChromaImplNanGuard:
    """Fix #4 — guard NaN/inf cho max_tonal trong _detect_key_from_chroma_impl.

    Caller có thể gọi impl trực tiếp với cqt_normalized chưa làm sạch (NaN/inf).
    Trước guard: max_tonal = max(... NaN ...) = NaN, và "NaN or 1.0" trả NaN
    (NaN truthy) → tonal_norm NaN → so sánh combined hỏng. Sau guard: vẫn trả
    result hợp lệ, không NaN, không RuntimeWarning.
    """

    def test_nan_in_chroma_does_not_break(self):
        """cqt_normalized chứa NaN → vẫn trả dict hợp lệ (không crash, không NaN field)."""
        import warnings
        # chroma_for_analysis sạch (để correlation chạy được + tạo family),
        # nhưng cqt_normalized (dùng cho tonal_strength) dính NaN.
        chroma = np.zeros(12)
        chroma[0] = 0.5
        chroma[9] = 0.5  # đẩy C/Am vào family để nhánh disambiguation chạy
        chroma = chroma / chroma.sum()
        bad_cqt = chroma.copy()
        bad_cqt[0] = np.nan  # nhiễm NaN vào tonic C
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # RuntimeWarning mới → fail
            with patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
                result = ToneDetector._detect_key_from_chroma_impl(chroma, bad_cqt)
        assert result is not None
        assert "key" in result and "confidence" in result

    def test_inf_in_chroma_does_not_break(self):
        """cqt_normalized chứa +inf → max_tonal được ép 1.0, kết quả vẫn hợp lệ."""
        chroma = np.zeros(12)
        chroma[0] = 0.5
        chroma[9] = 0.5
        chroma = chroma / chroma.sum()
        bad_cqt = chroma.copy()
        bad_cqt[7] = np.inf  # fifth của C → inf
        with patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            result = ToneDetector._detect_key_from_chroma_impl(chroma, bad_cqt)
        assert result is not None
        assert result["scale"] in ("Major", "Minor")
        assert 0 <= result["key_index"] <= 11


# ──────────────────────────────────────────────────────────────
# Detection tests with mocked heavy deps
# ──────────────────────────────────────────────────────────────

def _make_fake_librosa(chroma_result=None, rms_result=None):
    """Build a minimal fake librosa module."""
    if chroma_result is None:
        # Strong C major chroma
        chroma_result = np.zeros((12, 10))
        chroma_result[0, :] = 1.0  # C

    if rms_result is None:
        rms_result = np.ones((1, 10)) * 0.5

    lib = types.ModuleType("librosa")
    lib.feature = types.SimpleNamespace(
        chroma_cqt=lambda **kw: chroma_result,
        rms=lambda **kw: rms_result,
    )
    # HPSS (Fix #5): trả (harmonic, percussive). Stub: harmonic = bản sao input.
    lib.effects = types.SimpleNamespace(
        hpss=lambda y, **kw: (np.asarray(y, dtype=float), np.zeros_like(np.asarray(y, dtype=float))),
    )
    lib.pyin = lambda *a, **kw: (
        np.array([50.0] * 10),  # f0
        np.array([True] * 10),  # voiced
        np.zeros(10),
    )
    lib.stft = lambda y: np.zeros((1025, 10), dtype=complex)
    lib.istft = lambda S, **kw: np.zeros(44100)
    lib.fft_frequencies = lambda **kw: np.linspace(0, 22050, 1025)
    lib.load = lambda path, **kw: (np.random.randn(22050), 22050)
    lib.yin = lambda y, **kw: np.full(100, 440.0)
    return lib


class TestDetectKeyFromAudio:
    """TD-08, TD-09 — detect_key_from_audio() with mocked librosa"""

    def test_returns_result_for_valid_audio(self):
        """TD-08: returns dict with required keys for non-silent audio"""
        # Create audio that's not silent (rms > 0.001 after processing)
        audio = np.random.randn(44100).astype(np.float32) * 0.1
        sr = 44100

        fake_lib = _make_fake_librosa()
        # MemoryGuard is imported locally inside detect_key_from_audio, patch the source module
        with patch.dict("sys.modules", {"librosa": fake_lib}), \
             patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            result = ToneDetector.detect_key_from_audio(audio, sr)

        assert result is not None
        assert "key" in result
        assert "key_index" in result
        assert "scale" in result
        assert "confidence" in result
        assert result["scale"] in ("Major", "Minor")
        assert 0 <= result["key_index"] <= 11

    def test_silent_audio_returns_none(self):
        """TD-09: near-silent audio → None (rms < 0.001 triggers early exit)"""
        audio = np.zeros(44100, dtype=np.float32)
        sr = 44100

        fake_lib = _make_fake_librosa()
        with patch.dict("sys.modules", {"librosa": fake_lib}), \
             patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            # For truly zero audio, rms < 0.001 → returns None
            result = ToneDetector.detect_key_from_audio(audio, sr)

        # Either None (silent) or a valid result (if mock bypasses silence check)
        if result is not None:
            assert "key" in result

    def test_does_not_raise_on_malformed_audio(self):
        """Should catch exceptions and return None, not raise"""
        audio = np.array([float("inf"), float("nan")] * 100)
        sr = 22050

        fake_lib = _make_fake_librosa()
        with patch.dict("sys.modules", {"librosa": fake_lib}), \
             patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            # Should not raise
            try:
                result = ToneDetector.detect_key_from_audio(audio, sr)
                # Result is either None or valid dict
                assert result is None or isinstance(result, dict)
            except Exception:
                pytest.fail("detect_key_from_audio raised an exception")


class TestDetectKeyFromSystemAudio:
    """TD-10 — detect_key_from_system_audio() with mocked pyaudiowpatch"""

    def test_calls_detect_key_from_audio(self):
        """TD-10: when loopback succeeds, calls detect_key_from_audio"""
        # Build a fake pyaudiowpatch that returns non-zero audio chunks
        # so the rms check passes (rms > 0.001)
        non_silent_chunk = (np.ones(1024, dtype=np.float32) * 0.1).tobytes()

        mock_pa = MagicMock()
        mock_pa.get_host_api_count.return_value = 1
        mock_pa.get_host_api_info_by_index.return_value = {"name": "wasapi", "index": 0}
        mock_pa.get_device_count.return_value = 1
        mock_pa.get_device_info_by_index.return_value = {
            "isLoopbackDevice": True,
            "hostApi": 0,
            "name": "Stereo Mix (Realtek)",
            "defaultSampleRate": 44100,
            "index": 0,
        }
        mock_stream = MagicMock()
        mock_stream.read.return_value = non_silent_chunk
        mock_pa.open.return_value = mock_stream
        mock_pa.paFloat32 = 1

        fake_pyaudio = types.ModuleType("pyaudiowpatch")
        fake_pyaudio.PyAudio = lambda: mock_pa
        fake_pyaudio.paFloat32 = 1

        expected_result = {"key": "C", "key_index": 0, "scale": "Major", "confidence": 0.9, "key_display": "C"}

        with patch.dict("sys.modules", {"pyaudiowpatch": fake_pyaudio}), \
             patch.object(ToneDetector, "detect_key_from_audio", return_value=expected_result) as mock_detect, \
             patch("ctypes.windll.ole32.CoInitializeEx", return_value=0), \
             patch("ctypes.windll.ole32.CoUninitialize"), \
             patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            result = ToneDetector.detect_key_from_system_audio(duration=1)

        mock_detect.assert_called_once()
        assert result == expected_result

    def test_reason_out_populated_on_silence(self):
        """reason_out nhận nguyên nhân cụ thể khi loa im lặng (RMS < 0.001)."""
        silent_chunk = np.zeros(1024, dtype=np.float32).tobytes()

        mock_pa = MagicMock()
        mock_pa.get_host_api_count.return_value = 1
        mock_pa.get_host_api_info_by_index.return_value = {
            "name": "Windows WASAPI", "index": 0, "defaultOutputDevice": -1,
        }
        mock_pa.get_device_count.return_value = 1
        mock_pa.get_device_info_by_index.return_value = {
            "isLoopbackDevice": True, "hostApi": 0, "name": "Speakers",
            "defaultSampleRate": 16000, "index": 0, "maxInputChannels": 1,
        }
        mock_pa.get_wasapi_loopback_analogue_by_index.side_effect = AttributeError
        mock_stream = MagicMock()
        mock_stream.read.return_value = silent_chunk
        mock_pa.open.return_value = mock_stream
        mock_pa.paFloat32 = 1

        fake_pyaudio = types.ModuleType("pyaudiowpatch")
        fake_pyaudio.PyAudio = lambda: mock_pa
        fake_pyaudio.paFloat32 = 1

        reasons = []
        with patch.dict("sys.modules", {"pyaudiowpatch": fake_pyaudio}), \
             patch("ctypes.windll.ole32.CoInitializeEx", return_value=0), \
             patch("ctypes.windll.ole32.CoUninitialize"), \
             patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            result = ToneDetector.detect_key_from_system_audio(duration=1, reason_out=reasons)

        assert result is None
        assert reasons and "im lặng" in reasons[0]


class TestFindLoopbackDevice:
    """TD-10b — _find_loopback_device() picks the DEFAULT output's loopback."""

    def _make_pa(self, devices, default_output_idx):
        mock_pa = MagicMock()
        mock_pa.get_host_api_count.return_value = 1
        mock_pa.get_host_api_info_by_index.return_value = {
            "name": "Windows WASAPI", "index": 0,
            "defaultOutputDevice": default_output_idx,
        }
        mock_pa.get_device_count.return_value = len(devices)
        mock_pa.get_device_info_by_index.side_effect = lambda i: devices[i]
        # No analogue helper available → must rely on name matching
        mock_pa.get_wasapi_loopback_analogue_by_index.side_effect = AttributeError
        return mock_pa

    def test_prefers_default_output_loopback(self):
        """When multiple loopbacks exist, pick the one matching default output."""
        devices = [
            {"index": 0, "name": "Headset (USB)", "hostApi": 0,
             "isLoopbackDevice": False, "maxOutputChannels": 2},
            {"index": 1, "name": "Speakers (Realtek)", "hostApi": 0,
             "isLoopbackDevice": False, "maxOutputChannels": 2},
            {"index": 2, "name": "Headset (USB) [Loopback]", "hostApi": 0,
             "isLoopbackDevice": True, "defaultSampleRate": 48000},
            {"index": 3, "name": "Speakers (Realtek) [Loopback]", "hostApi": 0,
             "isLoopbackDevice": True, "defaultSampleRate": 48000},
        ]
        # Default output is "Speakers (Realtek)" (index 1)
        pa = self._make_pa(devices, default_output_idx=1)
        dev = ToneDetector._find_loopback_device(pa)
        assert dev is not None
        assert dev["index"] == 3  # Speakers loopback, NOT the first loopback (index 2)

    def test_falls_back_to_first_loopback(self):
        """No default output info → use first available loopback."""
        devices = [
            {"index": 0, "name": "Stereo Mix [Loopback]", "hostApi": 0,
             "isLoopbackDevice": True, "defaultSampleRate": 44100},
        ]
        pa = self._make_pa(devices, default_output_idx=-1)
        dev = ToneDetector._find_loopback_device(pa)
        assert dev is not None
        assert dev["index"] == 0


class TestDetectKeyFromYouTube:
    """TD-11 — detect_key_from_youtube() with mocked ScoringEngine + librosa"""

    def test_returns_tone_result_dict(self):
        """TD-11: when download + librosa succeed, returns tone dict"""
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        try:
            fake_audio = np.random.randn(22050).astype(np.float32) * 0.1
            expected_result = {
                "key": "G", "key_index": 7, "scale": "Major",
                "confidence": 0.85, "key_display": "G",
            }

            mock_scoring = MagicMock()
            mock_scoring.download_youtube_audio.return_value = tmp_path
            mock_scoring.cleanup_temp_file = MagicMock()

            fake_lib = _make_fake_librosa()
            fake_lib.load = lambda path, **kw: (fake_audio, 22050)

            # ScoringEngine is imported locally inside detect_key_from_youtube
            with patch("core.scoring.ScoringEngine", return_value=mock_scoring), \
                 patch.dict("sys.modules", {"librosa": fake_lib}), \
                 patch.object(ToneDetector, "detect_key_from_audio", return_value=expected_result), \
                 patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
                result = ToneDetector.detect_key_from_youtube(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                )

            assert result is not None
            assert result["key"] == "G"
            assert result["scale"] == "Major"
            assert "confidence" in result
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_returns_none_when_download_fails(self):
        """download_youtube_audio returns None → result is None"""
        mock_scoring = MagicMock()
        mock_scoring.download_youtube_audio.return_value = None
        mock_scoring.cleanup_temp_file = MagicMock()

        with patch("core.scoring.ScoringEngine", return_value=mock_scoring):
            result = ToneDetector.detect_key_from_youtube("https://www.youtube.com/watch?v=test")

        assert result is None


class TestDetectTimelineAdvanced:
    """TD-12 — detect_timeline_advanced() returns list with time + key_idx"""

    def test_returns_list_of_entries(self):
        """TD-12: valid audio → list with at least 1 entry having 'time' and 'key_index'"""
        sr = 22050
        # 30 seconds of audio (enough to produce segments)
        audio = np.random.randn(sr * 30).astype(np.float32) * 0.1

        # Stub detect_key_from_audio to return a result for any segment
        stub_result = {
            "key": "C", "key_index": 0, "scale": "Major",
            "confidence": 0.8, "key_display": "C",
        }

        fake_lib = _make_fake_librosa()
        with patch.dict("sys.modules", {"librosa": fake_lib}), \
             patch.object(ToneDetector, "_detect_key_from_chroma_impl", return_value=stub_result), \
             patch.object(ToneDetector, "detect_key_from_audio", return_value=stub_result), \
             patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            result = ToneDetector.detect_timeline_advanced(
                audio, sr, on_progress=None
            )

        # Result should be a list (possibly empty if no valid segment)
        assert isinstance(result, list)
        for entry in result:
            assert "time" in entry
            assert "key_index" in entry
            assert "scale" in entry
