"""Kiểm thử phần đọc chỉ số chất lượng của AudioRecorder."""
from core.recorder import AudioRecorder


def _recorder_with(stats_line):
    rec = AudioRecorder()
    rec._stats_line = stats_line
    return rec


def test_khong_co_stats_thi_khong_canh_bao():
    assert AudioRecorder().quality_warning() is None


def test_ban_thu_sach_thi_khong_canh_bao():
    rec = _recorder_with("STATS: drop=0 overrun=0 drift=0 limit=0.0000 gainmin=1.000")
    assert rec.quality_warning() is None


def test_thieu_mau_so_voi_thoi_gian_thi_bao_mat_tieng():
    # Driver vứt mẫu vì đói CPU: drop/overrun vẫn 0, chỉ capture lộ ra
    rec = _recorder_with(
        "STATS: drop=0 overrun=0 drift=0 limit=0.0000 gainmin=1.000 capture=0.809")
    warning = rec.quality_warning()
    assert warning and "mất tiếng" in warning


def test_thieu_khong_dang_ke_thi_khong_bao():
    rec = _recorder_with(
        "STATS: drop=0 overrun=0 drift=0 limit=0.0000 gainmin=1.000 capture=0.980")
    assert rec.quality_warning() is None


def test_mat_mau_thi_bao_may_qua_tai():
    rec = _recorder_with("STATS: drop=0 overrun=12 drift=0 limit=0.0000 gainmin=1.000")
    warning = rec.quality_warning()
    assert warning and "quá tải" in warning


def test_hang_doi_tran_cung_bao_qua_tai():
    rec = _recorder_with("STATS: drop=5 overrun=0 drift=0 limit=0.0000 gainmin=1.000")
    warning = rec.quality_warning()
    assert warning and "quá tải" in warning


def test_nen_nhe_thi_khong_lam_phien():
    # Bài hát to đều: limiter chạm liên tục nhưng chỉ hạ ~1 dB
    rec = _recorder_with("STATS: drop=0 overrun=0 drift=0 limit=0.8000 gainmin=0.890")
    assert rec.quality_warning() is None


def test_nen_sau_thi_bao_tieng_qua_lon():
    rec = _recorder_with("STATS: drop=0 overrun=0 drift=0 limit=0.6000 gainmin=0.410")
    warning = rec.quality_warning()
    assert warning and "quá lớn" in warning


def test_dong_stats_hong_thi_bo_qua_khong_no():
    rec = _recorder_with("STATS: drop=abc overrun= gainmin")
    assert rec.quality_warning() is None
