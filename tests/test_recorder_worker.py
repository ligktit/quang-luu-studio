"""Kiểm thử phần xử lý tín hiệu của recorder_worker (nguyên nhân tiếng rè)."""
import numpy as np
import pytest

from recorder_worker import (
    MIX_LB_GAIN,
    MIX_MIC_GAIN,
    PeakLimiter,
    StreamResampler,
)

FULL = 32767.0


def _stereo(mono):
    return np.column_stack([mono, mono]).astype(np.float32)


def _run_limiter(limiter, signal, block=2048):
    """Đẩy tín hiệu qua limiter theo từng block như vòng thu thật."""
    out = [limiter.process(signal[i:i + block]) for i in range(0, len(signal), block)]
    out.append(limiter.flush())
    return np.concatenate([c for c in out if c.shape[0]], axis=0)


# ── PeakLimiter ───────────────────────────────────────────────────────────────

def test_limiter_khong_dung_toi_tin_hieu_duoi_tran():
    rate = 48000
    t = np.arange(rate, dtype=np.float64) / rate
    src = _stereo(np.sin(2 * np.pi * 440 * t) * 0.5 * FULL)

    out = _run_limiter(PeakLimiter(), src)

    assert out.shape[0] == src.shape[0]
    np.testing.assert_allclose(out, src, atol=1e-3)


def test_limiter_giu_duoi_tran_khi_qua_dinh():
    """Tổng nhạc + giọng ở mức tệ nhất: 2 nguồn full-scale cộng vào nhau."""
    rate = 48000
    t = np.arange(rate * 2, dtype=np.float64) / rate
    total = (np.sin(2 * np.pi * 440 * t) * MIX_LB_GAIN
             + np.sin(2 * np.pi * 233 * t) * MIX_MIC_GAIN) * FULL

    limiter = PeakLimiter()
    out = _run_limiter(limiter, _stereo(total))

    assert np.max(np.abs(total)) > FULL          # đầu vào đúng là quá đỉnh
    assert np.max(np.abs(out)) <= FULL           # đầu ra không chạm mép
    assert limiter.limited_samples > 0


def test_limiter_meo_it_hon_han_np_clip():
    """Đo đúng thứ khách nghe thấy: hài bậc cao sinh ra khi quá đỉnh."""
    rate, freq = 48000, 440.0
    t = np.arange(rate, dtype=np.float64) / rate
    src = _stereo(np.sin(2 * np.pi * freq * t) * 1.6 * FULL)

    def harmonic_energy(sig):
        spec = np.abs(np.fft.rfft(sig.astype(np.float64)))
        fund = int(round(freq))          # 1 bin = 1Hz với 1 giây tín hiệu
        spec[fund - 3:fund + 4] = 0.0    # bỏ sóng cơ bản, còn lại là méo
        return float(np.sum(spec ** 2))

    limited = _run_limiter(PeakLimiter(), src)[:, 0]
    hard = np.clip(src[:, 0], -32768.0, 32767.0)

    assert harmonic_energy(limited) < harmonic_energy(hard) * 0.01


def test_limiter_khong_lam_mat_mau():
    rate = 48000
    src = _stereo(np.random.default_rng(0).uniform(-1.4, 1.4, rate) * FULL)
    out = _run_limiter(PeakLimiter(), src)
    assert out.shape[0] == src.shape[0]


def test_limiter_tha_gain_ve_sau_khi_het_qua_dinh():
    rate = 48000
    quiet = np.full(rate, 0.3 * FULL, dtype=np.float32)
    loud = np.full(rate // 10, 1.5 * FULL, dtype=np.float32)
    src = _stereo(np.concatenate([quiet, loud, quiet]))

    out = _run_limiter(PeakLimiter(), src)

    assert np.max(np.abs(out)) <= FULL
    # Sau ~1 giây kể từ lúc hết đoạn to, gain phải gần như về lại 1.0
    tail = out[-rate // 2:, 0]
    assert np.mean(tail) == pytest.approx(0.3 * FULL, rel=0.02)


# ── StreamResampler ───────────────────────────────────────────────────────────

def _chunks(signal, size):
    for i in range(0, len(signal), size):
        yield signal[i:i + size]


def _sine(n, freq, rate):
    t = np.arange(n, dtype=np.float64) / rate
    return _stereo(np.sin(2 * np.pi * freq * t) * 10000)


def test_resampler_giu_dung_ti_le_qua_nhieu_lo():
    """44.1kHz → 48kHz: tổng số mẫu ra phải khớp tỉ lệ, không trôi dần."""
    rate_in, rate_out = 44100, 48000
    src = _sine(rate_in * 10, 440.0, rate_in)  # 10 giây
    rs = StreamResampler(rate_out / rate_in)

    total = 0
    for chunk in _chunks(src, 941):
        total += rs.process(chunk).shape[0]

    expected = len(src) * rate_out / rate_in
    # Sai số cho phép: vài mẫu ở đuôi chưa nội suy được (~0.01% của 10 giây)
    assert abs(total - expected) < 50


def test_resampler_khong_gay_song_o_bien_lo():
    """Bản cũ dùng np.linspace cho từng lô → gãy sóng ở biên → nghe ra tiếng rè."""
    rate_in, rate_out = 44100, 48000
    src = _sine(rate_in * 2, 220.0, rate_in)
    rs = StreamResampler(rate_out / rate_in)

    out = np.concatenate([rs.process(c) for c in _chunks(src, 941)], axis=0)

    # Sóng 220Hz @48kHz: bước tối đa giữa 2 mẫu kề nhau ≈ 2π·220/48000 · biên độ
    max_step = 2 * np.pi * 220 / rate_out * 10000
    assert np.max(np.abs(np.diff(out[:, 0]))) < max_step * 1.2


def test_resampler_bao_toan_tan_so():
    rate_in, rate_out = 44100, 48000
    src = _sine(rate_in * 4, 1000.0, rate_in)
    rs = StreamResampler(rate_out / rate_in)
    out = np.concatenate([rs.process(c) for c in _chunks(src, 941)], axis=0)

    spectrum = np.abs(np.fft.rfft(out[:, 0]))
    peak_hz = np.fft.rfftfreq(out.shape[0], 1.0 / rate_out)[np.argmax(spectrum)]
    assert peak_hz == pytest.approx(1000.0, abs=2.0)


def test_resampler_giam_tan_so_cung_chay_duoc():
    """Mic 48kHz + loa 44.1kHz — chiều ngược lại (step > 1)."""
    rate_in, rate_out = 48000, 44100
    src = _sine(rate_in * 3, 440.0, rate_in)
    rs = StreamResampler(rate_out / rate_in)

    total = 0
    for chunk in _chunks(src, 1024):
        total += rs.process(chunk).shape[0]

    assert abs(total - len(src) * rate_out / rate_in) < 50


def test_resampler_chiu_duoc_lo_rong_khac_nhau():
    """Vòng drain gom số chunk khác nhau mỗi vòng → lô vào có độ dài thay đổi."""
    rate_in, rate_out = 44100, 48000
    src = _sine(rate_in * 2, 440.0, rate_in)
    rs = StreamResampler(rate_out / rate_in)

    total, i, size = 0, 0, 1
    while i < len(src):
        total += rs.process(src[i:i + size]).shape[0]
        i += size
        size = 1 + (size * 3) % 2500  # độ dài lô nhảy loạn xạ

    assert abs(total - len(src) * rate_out / rate_in) < 50


def test_resampler_lo_rong_khong_du_thi_giu_lai():
    rs = StreamResampler(48000 / 44100)
    assert rs.process(np.zeros((1, 2), dtype=np.float32)).shape[0] == 0
    assert rs.process(np.zeros((0, 2), dtype=np.float32)).shape[0] == 0
    # Đủ dữ liệu thì phần giữ lại được dùng tiếp, không mất mẫu
    assert rs.process(np.zeros((100, 2), dtype=np.float32)).shape[0] > 0
