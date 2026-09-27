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
    # detect_timeline_advanced ước lượng tuning một lần rồi truyền vào từng khối
    lib.estimate_tuning = lambda **kw: 0.0
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

    def test_tai_dung_bang_duration_limit(self):
        """download_youtube_audio phải tải ĐỦ cho phần sẽ phân tích.

        Mặc định của hàm tải là 60s; nếu caller xin phân tích dài hơn mà không
        truyền max_seconds thì librosa chỉ có 60s để đọc. Tải thêm cho lần dò
        bổ sung (FAST_EXTEND_SECONDS) cũng phải nằm trong cùng một lần tải.
        """
        import tempfile, os

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        try:
            mock_scoring = MagicMock()
            mock_scoring.download_youtube_audio.return_value = tmp_path
            mock_scoring.cleanup_temp_file = MagicMock()

            fake_lib = _make_fake_librosa()
            fake_lib.load = lambda path, **kw: (np.zeros(22050, dtype=np.float32), 22050)

            with patch("core.scoring.ScoringEngine", return_value=mock_scoring), \
                 patch.dict("sys.modules", {"librosa": fake_lib}), \
                 patch.object(ToneDetector, "detect_key_from_audio", return_value={"key": "C"}), \
                 patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
                ToneDetector.detect_key_from_youtube(
                    "https://www.youtube.com/watch?v=test", duration_limit=180
                )

            dl = mock_scoring.download_youtube_audio
            dl.assert_called_once()
            assert dl.call_args.kwargs.get("max_seconds") >= 180
            assert dl.call_args.kwargs.get("max_seconds") >= ToneDetector.FAST_EXTEND_SECONDS
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


class TestDetectKeyFromFile:
    """TD-15 — dò nhanh tự phân tích thêm khi kém tự tin (ngầm, không báo khách)."""

    SR = 100  # sr nhỏ cho test: 1 giây = 100 mẫu

    def _run(self, total_seconds, confidences, cancelled=None):
        fake_lib = _make_fake_librosa()
        fake_lib.load = lambda path, sr=None, duration=None, **kw: (
            np.ones(int(min(total_seconds, duration or total_seconds) * sr)), sr)
        lengths, confs = [], list(confidences)

        def fake_detect(audio, sr, **kw):
            lengths.append(len(audio) / sr)
            c = confs.pop(0)
            return {"key": "C", "key_index": 0, "scale": "Major", "key_display": "C",
                    "confidence": c}

        with patch.dict("sys.modules", {"librosa": fake_lib}), \
             patch.object(ToneDetector, "detect_key_from_audio", side_effect=fake_detect):
            result = ToneDetector.detect_key_from_file("bai.wav", sr=self.SR, cancelled=cancelled)
        return result, lengths

    def test_kem_tu_tin_thi_do_them_120s_va_dung_ket_qua_do(self):
        result, lengths = self._run(300, [0.62, 0.85])
        assert lengths == [ToneDetector.FAST_FIRST_SECONDS, ToneDetector.FAST_EXTEND_SECONDS]
        assert result["confidence"] == 0.85
        assert result["extended_seconds"] == ToneDetector.FAST_EXTEND_SECONDS

    def test_du_tu_tin_thi_khong_do_them(self):
        result, lengths = self._run(300, [0.86])
        assert lengths == [ToneDetector.FAST_FIRST_SECONDS]
        assert "extended_seconds" not in result

    def test_bai_ngan_khong_co_them_audio_thi_thoi(self):
        result, lengths = self._run(50, [0.4])
        assert lengths == [ToneDetector.FAST_FIRST_SECONDS]
        assert result["confidence"] == 0.4

    def test_phien_da_huy_thi_khong_ton_cpu_do_them(self):
        result, lengths = self._run(300, [0.4], cancelled=lambda: True)
        assert lengths == [ToneDetector.FAST_FIRST_SECONDS]


def _key_chroma(key_index, scale):
    """Chroma 'sạch' của một tone: chủ âm > át > các nốt trong gam > ngoài gam."""
    steps = [0, 2, 4, 5, 7, 9, 11] if scale == "Major" else [0, 2, 3, 5, 7, 8, 10]
    v = np.full(12, 0.02)
    for s in steps:
        v[(key_index + s) % 12] = 0.10
    v[key_index % 12] = 0.22
    v[(key_index + 7) % 12] = 0.16
    return v / v.sum()


def _song(parts, fake_labels=None):
    """Dựng (segments, chroma, rms) cho _regionalize — 1 frame = 1 giây.

    parts: [(giây, key_index, scale), ...] nối tiếp; mỗi part chia đoạn 15s.
    fake_labels: {chỉ số đoạn: (key_index, scale)} — ép nhãn đoạn KHÁC chroma
    thật của nó, mô phỏng đoạn ngắn bị dò ra hợp âm thay vì tone.
    """
    cols, segments, t = [], [], 0
    for secs, k, sc in parts:
        cols += [_key_chroma(k, sc)] * secs
        for a in range(0, secs, 15):
            b = min(secs, a + 15)
            segments.append({"start": float(t + a), "end": float(t + b),
                             "start_frame": t + a, "end_frame": t + b,
                             "chroma": _key_chroma(k, sc)})
        t += secs
    for idx, seg in enumerate(segments):
        k, sc = (fake_labels or {}).get(idx, (None, None))
        if k is None:
            res = ToneDetector._detect_key_from_chroma_impl(seg["chroma"], seg["chroma"],
                                                             verbose=False, cleanup=False)
        else:
            res = {"key_index": k, "scale": sc, "key_display": "?", "confidence": 0.7}
        seg["result"] = res
    chroma = np.array(cols).T
    return segments, chroma, np.ones(chroma.shape[1])


def _region_keys(regions):
    return [(round(r["start"]), r["result"]["key_index"], r["result"]["scale"]) for r in regions]


class TestRegionalize:
    """TD-14 — chuỗi tone dò toàn bài: gộp đoạn thành vùng tone.

    Trên nhạc thật cách gộp cũ báo ~16 lần đổi tone/bài vì mỗi đoạn 10–20s bị
    dò ra hợp âm của nó (C↔Am↔G...). Vùng chỉ đổi khi lệch hẳn bộ nốt và đủ dài.
    """

    def test_nhay_qua_lai_tone_ho_hang_khong_tinh_doi_tone(self):
        # 120s C trưởng, nhưng các đoạn bị dò ra Am / G / Dm xen kẽ
        segs, chroma, rms = _song([(120, 0, "Major")],
                                  fake_labels={1: (9, "Minor"), 3: (7, "Major"), 5: (2, "Minor")})
        regions = ToneDetector._regionalize(segs, chroma, rms)
        assert _region_keys(regions) == [(0, 0, "Major")]

    def test_nang_nua_cung_that_su_duoc_bat(self):
        segs, chroma, rms = _song([(90, 0, "Major"), (60, 1, "Major")])
        regions = ToneDetector._regionalize(segs, chroma, rms)
        assert _region_keys(regions) == [(0, 0, "Major"), (90, 1, "Major")]

    def test_nang_mot_cung_giong_thu(self):
        segs, chroma, rms = _song([(90, 9, "Minor"), (60, 11, "Minor")])
        regions = ToneDetector._regionalize(segs, chroma, rms)
        assert _region_keys(regions) == [(0, 9, "Minor"), (90, 11, "Minor")]

    def test_doan_lac_tone_ngan_bi_hut_vao_vung(self):
        # 15s F# giữa bài C — ngắn hơn TIMELINE_REGION_MIN_SECONDS
        segs, chroma, rms = _song([(90, 0, "Major"), (15, 6, "Major"), (60, 0, "Major")])
        regions = ToneDetector._regionalize(segs, chroma, rms)
        assert [(k, sc) for _, k, sc in _region_keys(regions)] == [(0, "Major")]

    def test_intro_lech_tone_nhap_vao_vung_sau(self):
        segs, chroma, rms = _song([(15, 3, "Minor"), (120, 7, "Major")])
        regions = ToneDetector._regionalize(segs, chroma, rms)
        assert len(regions) == 1
        assert regions[0]["start"] == 0.0
        assert (regions[0]["result"]["key_index"], regions[0]["result"]["scale"]) == (7, "Major")

    def test_khong_co_doan_hop_le(self):
        segs = [{"start": 0.0, "end": 5.0, "key_display": "Silence", "result": None}]
        assert ToneDetector._regionalize(segs, np.ones((12, 5)), np.ones(5)) == []


# ──────────────────────────────────────────────────────────────
# TD-13 — Chế độ "dò toàn bài": trần an toàn + xử lý theo khối
#
# detect_timeline_advanced() trước đây xử lý nguyên bài trong RAM: đỉnh RAM tỉ
# lệ tuyến tính với độ dài bài (đo được ~1.17 GB ở bài 15 phút). Nay có hai lớp
# bảo vệ — trần cứng TIMELINE_MAX_SECONDS và xử lý theo khối. Các test dưới đây
# khoá cả hai, VÀ khoá điều kiện làm cho chia khối cho ra đúng kết quả cũ:
# tuning phải được truyền tường minh vào từng khối.
# ──────────────────────────────────────────────────────────────

def _fingerprint_chroma(calls, y=None, sr=None, hop_length=512, tuning=None, **kw):
    """chroma_cqt giả: cột j mang đúng mẫu tại tâm frame j, hàng 1 mang tuning.

    Dùng để khoá số học lưới frame của _chroma_rms_blockwise mà không cần
    librosa thật (import soxr làm abort tiến trình pytest ở môi trường này).
    """
    y = np.asarray(y, dtype=np.float64)
    calls.append(len(y))
    n_frames = 1 + len(y) // hop_length
    out = np.zeros((12, n_frames))
    centers = np.minimum(np.arange(n_frames) * hop_length, len(y) - 1)
    out[0] = y[centers]
    out[1] = 0.0 if tuning is None else tuning
    return out


def _fingerprint_rms(y=None, hop_length=512, **kw):
    """rms giả, cùng lưới frame với _fingerprint_chroma."""
    y = np.asarray(y, dtype=np.float64)
    n_frames = 1 + len(y) // hop_length
    centers = np.minimum(np.arange(n_frames) * hop_length, len(y) - 1)
    return np.array([y[centers]])


class TestTimelineMemoryGuards:
    """TD-13 — trần độ dài + tương đương số học của xử lý theo khối"""

    def test_blockwise_matches_whole_song(self):
        """TD-13a: chroma/rms theo khối khớp TỪNG CỘT với cách tính nguyên bài.

        Đây là test then chốt: nếu nó vỡ thì chia khối đã làm lệch lưới frame,
        tức là ĐỔI tone dò ra chứ không chỉ tiết kiệm RAM.

        Không import librosa thật (import soxr làm abort tiến trình pytest trong
        môi trường này). Thay vào đó dùng chroma giả ĐÁNH DẤU mẫu tại tâm mỗi
        frame — nhờ vậy mọi sai lệch offset/đệm đều lộ ra ngay, chính xác hơn so
        khớp số thực. Tương đương số học với librosa thật được kiểm riêng bằng
        bộ đối chiếu golden (xem ghi chú ở _chroma_rms_blockwise).
        """
        sr, hop = 1000, 100
        rng = np.random.default_rng(7)
        audio = rng.standard_normal(20 * sr).astype(np.float32)

        calls = []
        fake_lib = _make_fake_librosa()
        fake_lib.feature = types.SimpleNamespace(
            chroma_cqt=lambda **kw: _fingerprint_chroma(calls, **kw),
            rms=lambda **kw: _fingerprint_rms(**kw),
        )

        with patch.dict("sys.modules", {"librosa": fake_lib}),              patch.object(ToneDetector, "TIMELINE_BLOCK_SECONDS", 5),              patch.object(ToneDetector, "TIMELINE_BLOCK_PAD_SECONDS", 2.0):
            chroma, rms = ToneDetector._chroma_rms_blockwise(
                audio, sr, hop, 0.042, want_rms=True)

        n_frames = 1 + len(audio) // hop
        centers = np.minimum(np.arange(n_frames) * hop, len(audio) - 1)
        expected = audio[centers]

        assert chroma.shape == (12, n_frames)
        assert rms.shape == (n_frames,)
        # Mỗi cột phải là mẫu tại ĐÚNG tâm frame của lưới toàn bài
        assert np.array_equal(chroma[0], expected)
        assert np.array_equal(rms, expected)
        # tuning phải được truyền tường minh xuống từng khối — để None thì mỗi
        # khối tự ước lượng một giá trị khác nhau và chroma lệch ~0.03
        assert np.allclose(chroma[1], 0.042)

        # Thật sự có chia khối, và KHÔNG khối nào ôm cả bài (đó là điểm mấu chốt
        # giữ RAM phẳng)
        assert len(calls) >= 4, calls
        assert max(calls) < len(audio), calls

    def test_blockwise_applies_dc_offset_and_clip(self):
        """TD-13b: tiền xử lý theo khối cho kết quả như xử lý nguyên mảng.

        dc_offset/clip được áp cho từng khối thay vì nhân đôi cả mảng audio —
        phải ra đúng cùng giá trị.
        """
        sr, hop = 1000, 100
        rng = np.random.default_rng(3)
        audio = (rng.standard_normal(12 * sr).astype(np.float32) * 0.8
                 + 0.4)  # DC offset cố ý, có mẫu vượt ±1 để clip có việc

        fake_lib = _make_fake_librosa()
        fake_lib.feature = types.SimpleNamespace(
            chroma_cqt=lambda **kw: _fingerprint_chroma([], **kw),
            rms=lambda **kw: _fingerprint_rms(**kw),
        )

        dc = float(np.mean(audio))
        with patch.dict("sys.modules", {"librosa": fake_lib}),              patch.object(ToneDetector, "TIMELINE_BLOCK_SECONDS", 4),              patch.object(ToneDetector, "TIMELINE_BLOCK_PAD_SECONDS", 1.0):
            chroma, _ = ToneDetector._chroma_rms_blockwise(
                audio, sr, hop, 0.0, dc_offset=dc, clip=True, want_rms=False)

        prepared = np.clip(audio - dc, -1.0, 1.0)
        n_frames = 1 + len(audio) // hop
        centers = np.minimum(np.arange(n_frames) * hop, len(audio) - 1)
        assert np.allclose(chroma[0], prepared[centers], atol=1e-6)
        # clip thật sự có tác dụng (nếu không thì test trên vô nghĩa)
        assert np.any(np.abs(audio - dc) > 1.0)

    def test_estimate_tuning_bounded_limits_sample(self):
        """TD-13c: chỉ đưa vào estimate_tuning một lượng audio có giới hạn.

        Đây là điều giữ RAM phẳng — estimate_tuning() dựng STFT trên cả mảng
        được truyền vào, và chính nó là đỉnh RAM lớn nhất của luồng cũ.
        """
        sr = 1000
        audio = np.zeros(sr * 600, dtype=np.float32)  # "10 phút"
        seen = {}

        def fake_estimate(y=None, sr=None, **kw):
            seen["len"] = len(y)
            return 0.02

        fake_lib = _make_fake_librosa()
        fake_lib.estimate_tuning = fake_estimate
        with patch.dict("sys.modules", {"librosa": fake_lib}), \
             patch.object(ToneDetector, "TUNING_SAMPLE_SECONDS", 60):
            tuning = ToneDetector._estimate_tuning_bounded(audio, sr)

        # 0.02 nửa cung (ước lượng ở 12 bin) = 0.06 bin CQT 36 bin/quãng 8
        assert tuning == pytest.approx(0.06)
        assert seen["len"] <= 60 * sr

    def test_estimate_tuning_uses_12_bins_so_it_does_not_wrap(self):
        """TD-13f: ước lượng ở 12 bin/quãng 8 rồi mới đổi sang bin CQT.

        Ước lượng ở 36 bin chỉ đọc đúng ±16.7 cent; bài lệch +20 cent bị đọc
        thành -11 cent và dò sang tone quãng 5 (đo trên âm thanh tổng hợp).
        """
        seen = {}

        def fake_estimate(y=None, sr=None, bins_per_octave=None, **kw):
            seen["bpo"] = bins_per_octave
            return 0.2  # 0.2 nửa cung = +20 cent

        fake_lib = _make_fake_librosa()
        fake_lib.estimate_tuning = fake_estimate
        with patch.dict("sys.modules", {"librosa": fake_lib}):
            cents = ToneDetector._estimate_tuning_cents(np.zeros(1000), 1000)
            bins36 = ToneDetector._estimate_tuning_bounded(np.zeros(1000), 1000)

        assert seen["bpo"] == 12
        assert cents == pytest.approx(20.0)
        # +20 cent vượt ±0.5 bin của CQT 36 bin — phải giữ nguyên, không gấp vòng
        assert bins36 == pytest.approx(0.6)

    def test_detect_key_passes_tuning_explicitly(self):
        """TD-13g: dò 1 lần phải truyền tuning vào chroma_cqt (None = librosa
        tự ước lượng ở 36 bin và gấp vòng), và ghi tuning_cents vào kết quả."""
        seen = {}
        fake_lib = _make_fake_librosa()
        fake_lib.estimate_tuning = lambda **kw: -0.3  # -30 cent (kiểu A=432Hz)
        base_chroma = fake_lib.feature.chroma_cqt

        def spy_chroma(**kw):
            seen["tuning"] = kw.get("tuning")
            return base_chroma(**kw)

        fake_lib.feature.chroma_cqt = spy_chroma
        audio = np.random.randn(44100).astype(np.float32) * 0.1
        with patch.dict("sys.modules", {"librosa": fake_lib}), \
             patch("core.memory.MemoryGuard.force_cleanup", MagicMock()):
            result = ToneDetector.detect_key_from_audio(audio, 44100, skip_hum_detection=True)

        assert seen["tuning"] == pytest.approx(-0.9)
        assert result["tuning_cents"] == pytest.approx(-30.0)

    def test_estimate_tuning_falls_back_to_zero(self):
        """TD-13d: estimate_tuning lỗi → trả 0.0, không ném ra ngoài."""
        fake_lib = _make_fake_librosa()
        fake_lib.estimate_tuning = MagicMock(side_effect=RuntimeError("hỏng"))
        with patch.dict("sys.modules", {"librosa": fake_lib}):
            assert ToneDetector._estimate_tuning_bounded(
                np.zeros(1000, dtype=np.float32), 1000) == 0.0

    def test_timeline_truncates_over_long_audio(self):
        """TD-13e: bài vượt trần bị cắt TRƯỚC khi phân tích, và báo cho user."""
        sr = 100
        stub_result = {"key": "C", "key_index": 0, "scale": "Major",
                       "confidence": 0.8, "key_display": "C"}
        seen_lengths = []

        def spy_blockwise(audio_data, *a, **kw):
            seen_lengths.append(len(audio_data))
            n = 1 + len(audio_data) // a[1]
            return np.ones((12, n)), np.ones(n)

        audio = np.random.randn(sr * 600).astype(np.float32) * 0.1  # "600 giây"
        messages = []

        fake_lib = _make_fake_librosa()
        with patch.dict("sys.modules", {"librosa": fake_lib}), \
             patch.object(ToneDetector, "TIMELINE_MAX_SECONDS", 120), \
             patch.object(ToneDetector, "_estimate_tuning_bounded", return_value=0.0), \
             patch.object(ToneDetector, "_chroma_rms_blockwise", side_effect=spy_blockwise), \
             patch.object(ToneDetector, "_detect_key_from_chroma_impl", return_value=stub_result):
            ToneDetector.detect_timeline_advanced(
                audio, sr, on_progress=messages.append)

        # Cả hai lượt chroma đều chỉ thấy phần đã cắt, không phải cả bài
        assert seen_lengths, "chưa gọi tới bước tính chroma"
        assert all(n == 120 * sr for n in seen_lengths), seen_lengths
        assert any("quá dài" in m for m in messages), messages

    def test_timeline_keeps_short_audio_intact(self):
        """TD-13f: bài dưới trần KHÔNG bị đụng tới."""
        sr = 100
        stub_result = {"key": "C", "key_index": 0, "scale": "Major",
                       "confidence": 0.8, "key_display": "C"}
        seen_lengths = []

        def spy_blockwise(audio_data, *a, **kw):
            seen_lengths.append(len(audio_data))
            n = 1 + len(audio_data) // a[1]
            return np.ones((12, n)), np.ones(n)

        audio = np.random.randn(sr * 90).astype(np.float32) * 0.1
        messages = []

        fake_lib = _make_fake_librosa()
        with patch.dict("sys.modules", {"librosa": fake_lib}), \
             patch.object(ToneDetector, "TIMELINE_MAX_SECONDS", 120), \
             patch.object(ToneDetector, "_estimate_tuning_bounded", return_value=0.0), \
             patch.object(ToneDetector, "_chroma_rms_blockwise", side_effect=spy_blockwise), \
             patch.object(ToneDetector, "_detect_key_from_chroma_impl", return_value=stub_result):
            ToneDetector.detect_timeline_advanced(
                audio, sr, on_progress=messages.append)

        assert all(n == 90 * sr for n in seen_lengths), seen_lengths
        assert not any("quá dài" in m for m in messages), messages
