"""Bộ chẩn đoán khâu tải (--thu-tai) — chạy trên máy khách, không được treo.

Nhật ký 16/09/2026 cho thấy dò tone chết ở khâu tải nhưng app không ghi lại
yt-dlp nói gì (logger yt_dlp bị ghim ERROR, thông điệp đi vào log.debug). Bộ
chẩn đoán này là mắt của ta ở máy khách, nên bản thân nó phải chắc: không treo
vô hạn, và kết luận phải khớp với hiện tượng.

Không test nào chạm mạng: ScoringEngine được thay bằng bản giả.
"""

import time

import pytest

from core import download_check as dc


class _MayGia:
    """ScoringEngine giả — thay cho việc tải thật."""

    ket_qua = ("C:/tmp/a.wav", "Bài Test")
    treo = 0.0
    loi = None

    def download_youtube_audio_with_info(self, url, output_dir=None, extra_opts=None):
        _MayGia.da_nhan_extra = extra_opts
        if _MayGia.treo:
            time.sleep(_MayGia.treo)
        if _MayGia.loi:
            raise _MayGia.loi
        return _MayGia.ket_qua

    def cleanup_temp_file(self):
        pass


@pytest.fixture
def may_gia(monkeypatch):
    import core.scoring as scoring

    _MayGia.treo, _MayGia.loi = 0.0, None
    _MayGia.ket_qua = ("C:/tmp/a.wav", "Bài Test")
    _MayGia.da_nhan_extra = None
    monkeypatch.setattr(scoring, "ScoringEngine", _MayGia)
    monkeypatch.setattr(dc, "_NHIP_BAO", 0.05)
    return _MayGia


def test_tai_xong_thi_bao_thoi_gian(may_gia, tmp_path, monkeypatch):
    file_gia = tmp_path / "a.wav"
    file_gia.write_bytes(b"x" * 2048)
    may_gia.ket_qua = (str(file_gia), "Bài Test")

    bb = dc._BienBan()
    ket_qua, giay = dc._chang_tai(bb, "https://youtu.be/abc")

    assert ket_qua and ket_qua["duong_dan"] == str(file_gia)
    assert giay < 10
    assert "Xong sau" in bb.van_ban()


def test_gan_duoc_den_vao_duong_app_di(may_gia):
    """Phải truyền logger + progress_hooks xuống đúng hàm tải mà app dùng."""
    dc._chang_tai(dc._BienBan(), "https://youtu.be/abc")

    extra = may_gia.da_nhan_extra
    assert extra and "logger" in extra and extra["progress_hooks"]


def test_treo_qua_tran_thi_bo_cuoc(may_gia, monkeypatch):
    """Treo mãi ở máy khách thì bộ chẩn đoán phải tự thoát, không đứng hình."""
    monkeypatch.setattr(dc, "_TRAN_GIAY", 0.2)
    may_gia.treo = 30            # luồng nền là daemon, không giữ tiến trình lại

    t0 = time.time()
    ket_qua, giay = dc._chang_tai(dc._BienBan(), "https://youtu.be/abc")

    assert ket_qua is None
    assert time.time() - t0 < 5, "bỏ cuộc quá muộn"
    assert giay >= 0.2


def test_loi_khi_tai_duoc_ghi_lai(may_gia):
    may_gia.loi = RuntimeError("HTTP Error 403: Forbidden")

    bb = dc._BienBan()
    ket_qua, _ = dc._chang_tai(bb, "https://youtu.be/abc")

    assert ket_qua is None
    assert "403" in bb.van_ban()


def test_khong_ra_file_van_bao_ro(may_gia):
    """yt-dlp nuốt lỗi và trả (None, '') — đúng ca đang xảy ra ở máy khách."""
    may_gia.ket_qua = (None, "")

    bb = dc._BienBan()
    ket_qua, _ = dc._chang_tai(bb, "https://youtu.be/abc")

    assert ket_qua is None
    assert "KHÔNG RA FILE" in bb.van_ban()


# ── Kết luận phải khớp hiện tượng ─────────────────────────────────────────────

def test_ket_luan_tai_nhanh():
    bb = dc._BienBan()
    dc._ket_luan(bb, True, {"title": "x"}, 2.0, {"duong_dan": "a.wav"}, 3.0)
    assert "KHÔNG phải thủ phạm" in bb.van_ban()


def test_ket_luan_tai_duoc_nhung_qua_cham():
    bb = dc._BienBan()
    dc._ket_luan(bb, True, {"title": "x"}, 2.0, {"duong_dan": "a.wav"}, 120.0)
    assert "quá hạn 90 giây" in bb.van_ban()


def test_ket_luan_thieu_ffmpeg():
    bb = dc._BienBan()
    dc._ket_luan(bb, False, {"title": "x"}, 2.0, None, 95.0)
    assert "KHÔNG có ffmpeg" in bb.van_ban()


def test_ket_luan_hong_tu_chang_metadata():
    bb = dc._BienBan()
    dc._ket_luan(bb, True, None, 90.0, None, 0.0)
    assert "chặng LẤY THÔNG TIN" in bb.van_ban()


# ── Tuỳ chọn thêm không được làm hỏng đường gọi cũ ────────────────────────────

def test_extra_opts_ngam_vao_ydl_opts(monkeypatch, tmp_path):
    """extra_opts phải tới được make_ydl_opts, và caller cũ không truyền vẫn chạy."""
    from core import scoring

    ghi_nhan = {}

    def make_gia(**opts):
        ghi_nhan.update(opts)
        return dict(opts)

    monkeypatch.setattr(scoring, "make_ydl_opts", make_gia)
    monkeypatch.setattr(scoring, "extract_info_with_auth",
                        lambda *a, **k: {"title": "Bài Test"})

    may = scoring.ScoringEngine()
    may.download_youtube_audio_with_info("https://youtu.be/abc", output_dir=str(tmp_path),
                                         extra_opts={"logger": "ĐÈN"})
    assert ghi_nhan.get("logger") == "ĐÈN"

    ghi_nhan.clear()
    may.download_youtube_audio_with_info("https://youtu.be/abc", output_dir=str(tmp_path))
    assert "logger" not in ghi_nhan
